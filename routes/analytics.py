from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func, distinct
from dependencies import get_db
import models
from datetime import datetime, timedelta, timezone
from typing import Optional
from collections import defaultdict

router = APIRouter()

# Constants for timezone
INDIA_OFFSET = timedelta(hours=5, minutes=30)  # UTC+5:30 for India
INDIA_TIMEZONE = timezone(INDIA_OFFSET)

def get_hour_range(hour: int) -> str:
    """Convert hour to time range string"""
    return f"{hour:02d}:00-{(hour+1):02d}:00"

def get_current_time():
    """Get current time in IST"""
    return datetime.now(INDIA_TIMEZONE)

def convert_to_system_time(dt: datetime) -> datetime:
    """Convert UTC time to IST"""
    if dt.tzinfo is None:  # If naive datetime
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(INDIA_TIMEZONE)

def validate_date_range(start_date: Optional[datetime], end_date: Optional[datetime]) -> tuple:
    """Validate and convert date range to IST"""
    if not end_date:
        end_date = get_current_time()
    else:
        end_date = convert_to_system_time(end_date)
    
    if not start_date:
        start_date = end_date - timedelta(days=30)
    else:
        start_date = convert_to_system_time(start_date)
    
    # Normalize time ranges
    start_date = start_date.replace(hour=0, minute=0, second=0, microsecond=0)
    end_date = end_date.replace(hour=23, minute=59, second=59, microsecond=999999)
    
    return start_date, end_date

@router.get("/analytics")
def get_analytics(
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    institution_id: Optional[int] = None,
    user_id: Optional[int] = None,
    db: Session = Depends(get_db)
):
    try:
        # Initialize date range with IST
        start_date, end_date = validate_date_range(start_date, end_date)

        # Build base query filters
        base_filters = [
            models.FinalRecords.entry_date.between(start_date.date(), end_date.date())
        ]
        if institution_id:
            base_filters.append(models.User.institution_id == institution_id)
        if user_id:
            base_filters.append(models.FinalRecords.user_id == user_id)

        # Initialize statistics containers
        stats = {
            'hourly_stats': defaultdict(lambda: {
                'total_entries': 0,
                'successful_entries': 0,
                'failed_entries': 0,
                'bypass_entries': 0,
                'peak_traffic': 0
            }),
            'verification_stats': {
                'total_attempts': 0,
                'face_success': 0,
                'qr_success': 0,
                'both_success': 0,
                'failures': 0
            },
            'entry_types': {
                'normal': 0,
                'bypass': 0,
                'group': 0
            },
            'duration_stats': [],
            'daily_stats': defaultdict(lambda: {
                'entries': 0,
                'unique_users': set(),
                'success_rate': 0,
                'bypass_count': 0
            }),
            'scan_completion_times': [],  # For storing valid scan completion times
            'recent_scan_times': []      # For storing last 10 entries
        }

        # Process records with timezone awareness
        records = db.query(models.FinalRecords).filter(*base_filters).order_by(
            models.FinalRecords.entry_date.desc()
        ).all()
        
        for record in records:
            for log in record.time_logs:
                # Convert arrival time to system timezone
                arrival_time = convert_to_system_time(datetime.fromisoformat(log['arrival']))
                hour = arrival_time.hour
                date_str = arrival_time.date().isoformat()

                # Track hourly statistics
                stats['hourly_stats'][hour]['total_entries'] += 1
                stats['hourly_stats'][hour]['peak_traffic'] = max(
                    stats['hourly_stats'][hour]['peak_traffic'],
                    stats['hourly_stats'][hour]['total_entries']
                )

                # Track entry types
                entry_type = log.get('entry_type', 'normal')
                stats['entry_types'][entry_type] += 1
                if entry_type == 'bypass':
                    stats['hourly_stats'][hour]['bypass_entries'] += 1

                # Track verifications
                stats['verification_stats']['total_attempts'] += 1
                if log.get('face_verified'):
                    stats['verification_stats']['face_success'] += 1
                if log.get('qr_verified'):
                    stats['verification_stats']['qr_success'] += 1
                if log.get('face_verified') and log.get('qr_verified'):
                    stats['verification_stats']['both_success'] += 1
                    stats['hourly_stats'][hour]['successful_entries'] += 1
                else:
                    stats['verification_stats']['failures'] += 1
                    stats['hourly_stats'][hour]['failed_entries'] += 1

                # Track daily statistics
                stats['daily_stats'][date_str]['entries'] += 1
                stats['daily_stats'][date_str]['unique_users'].add(record.user_id)
                if entry_type == 'bypass':
                    stats['daily_stats'][date_str]['bypass_count'] += 1

                # Calculate scan completion time (time between QR scan and face verification)
                if log.get('arrival') and log.get('face_verification_time'):
                    arrival_time = convert_to_system_time(datetime.fromisoformat(log['arrival']))
                    face_time = convert_to_system_time(datetime.fromisoformat(log['face_verification_time']))
                    
                    # Calculate time difference in minutes
                    time_diff = (face_time - arrival_time).total_seconds() / 60
                    
                    # Only consider entries completed within 3 minutes
                    if 0 <= time_diff <= 3:
                        stats['scan_completion_times'].append(time_diff)
                        
                        # Store recent scan times (we'll take last 10 later)
                        stats['recent_scan_times'].append({
                            'date': arrival_time.date().isoformat(),
                            'completion_time': time_diff
                        })

                # Track duration if available with timezone awareness
                if log.get('departure'):
                    arrival = convert_to_system_time(datetime.fromisoformat(log['arrival']))
                    departure = convert_to_system_time(datetime.fromisoformat(log['departure']))
                    duration = (departure - arrival).total_seconds() / 60  # Convert to minutes
                    stats['duration_stats'].append(duration)

        # Calculate peak hours (hours with at least 80% of max traffic)
        max_traffic = max((s['total_entries'] for s in stats['hourly_stats'].values()), default=0)
        peak_hours = [
            get_hour_range(hour) 
            for hour, data in stats['hourly_stats'].items() 
            if data['total_entries'] >= max_traffic * 0.8
        ]

        # Calculate success rates and metrics
        total_entries = sum(stats['entry_types'].values())
        avg_duration = sum(stats['duration_stats']) / len(stats['duration_stats']) if stats['duration_stats'] else 0

        # Calculate averages
        avg_completion_time = (
            sum(stats['scan_completion_times']) / len(stats['scan_completion_times'])
            if stats['scan_completion_times'] else 0
        )

        # Get last 10 valid scan completion times
        recent_scans = stats['recent_scan_times'][-10:] if stats['recent_scan_times'] else []
        avg_recent_completion_time = (
            sum(scan['completion_time'] for scan in recent_scans) / len(recent_scans)
            if recent_scans else 0
        )

        return {
            "time_range": {
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
                "timezone": "Asia/Kolkata (UTC+5:30)"
            },
            "traffic_analysis": {
                "peak_hours": peak_hours,
                "hourly_distribution": {
                    get_hour_range(hour): data 
                    for hour, data in stats['hourly_stats'].items()
                },
                "busiest_periods": [
                    get_hour_range(hour) 
                    for hour, data in sorted(
                        stats['hourly_stats'].items(), 
                        key=lambda x: x[1]['total_entries'], 
                        reverse=True
                    )[:3]
                ]
            },
            "performance_metrics": {
                "success_rate": round(
                    stats['verification_stats']['both_success'] / stats['verification_stats']['total_attempts'] * 100 
                    if stats['verification_stats']['total_attempts'] > 0 else 0, 2
                ),
                "face_verification_rate": round(
                    stats['verification_stats']['face_success'] / stats['verification_stats']['total_attempts'] * 100
                    if stats['verification_stats']['total_attempts'] > 0 else 0, 2
                ),
                "qr_verification_rate": round(
                    stats['verification_stats']['qr_success'] / stats['verification_stats']['total_attempts'] * 100
                    if stats['verification_stats']['total_attempts'] > 0 else 0, 2
                ),
                "bypass_rate": round(
                    stats['entry_types']['bypass'] / total_entries * 100
                    if total_entries > 0 else 0, 2
                )
            },
            "scan_efficiency": {
                "average_completion_time_minutes": round(avg_completion_time, 2),
                "recent_average_completion_time_minutes": round(avg_recent_completion_time, 2),
                "recent_scans": recent_scans,
                "total_valid_scans": len(stats['scan_completion_times']),
                "completion_rate_within_3min": round(
                    len(stats['scan_completion_times']) / stats['verification_stats']['total_attempts'] * 100
                    if stats['verification_stats']['total_attempts'] > 0 else 0, 2
                )
            },
            "entry_statistics": {
                "total_entries": total_entries,
                "entry_types": stats['entry_types'],
                "average_duration_minutes": round(avg_duration, 2),  # Changed to minutes
                "daily_patterns": {
                    date: {
                        "entries": data['entries'],
                        "unique_users": len(data['unique_users']),
                        "bypass_rate": round(
                            data['bypass_count'] / data['entries'] * 100
                            if data['entries'] > 0 else 0, 2
                        )
                    }
                    for date, data in stats['daily_stats'].items()
                }
            },
            "verification_summary": {
                "total_attempts": stats['verification_stats']['total_attempts'],
                "successful_verifications": stats['verification_stats']['both_success'],
                "failed_verifications": stats['verification_stats']['failures'],
                "verification_rates": {
                    "face": round(
                        stats['verification_stats']['face_success'] / stats['verification_stats']['total_attempts'] * 100
                        if stats['verification_stats']['total_attempts'] > 0 else 0, 2
                    ),
                    "qr": round(
                        stats['verification_stats']['qr_success'] / stats['verification_stats']['total_attempts'] * 100
                        if stats['verification_stats']['total_attempts'] > 0 else 0, 2
                    ),
                    "both": round(
                        stats['verification_stats']['both_success'] / stats['verification_stats']['total_attempts'] * 100
                        if stats['verification_stats']['total_attempts'] > 0 else 0, 2
                    )
                }
            }
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Analytics error: {str(e)}")

@router.get("/analytics/overview")
def get_analytics_overview(
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    institution_id: Optional[int] = None,
    db: Session = Depends(get_db)
):
    try:
        # Set default date range if not provided (last 30 days)
        if not end_date:
            end_date = datetime.utcnow()
        if not start_date:
            start_date = end_date - timedelta(days=30)

        # Base query filters
        base_filters = [
            models.FinalRecords.entry_date.between(start_date.date(), end_date.date())
        ]

        if institution_id:
            base_filters.append(models.User.institution_id == institution_id)

        # General Statistics
        general_stats = db.query(
            func.count(distinct(models.FinalRecords.user_id)).label('total_unique_users'),
            func.count(distinct(models.FinalRecords.entry_date)).label('total_active_days'),
        ).join(
            models.User,
            models.User.user_id == models.FinalRecords.user_id
        ).filter(*base_filters).first()

        # Entry Type Distribution
        entries_by_type = []
        for record in db.query(models.FinalRecords).filter(*base_filters).all():
            for log in record.time_logs:
                entries_by_type.append(log.get('entry_type', 'normal'))

        entry_distribution = {
            'normal': entries_by_type.count('normal'),
            'bypass': entries_by_type.count('bypass'),
            'group': len([e for e in entries_by_type if 'group_entry' in str(e)])
        }

        # Time Analysis
        time_analysis = {
            'average_duration': timedelta(0),
            'total_entries': 0,
            'completed_entries': 0
        }

        for record in db.query(models.FinalRecords).filter(*base_filters).all():
            for log in record.time_logs:
                time_analysis['total_entries'] += 1
                if log.get('departure'):
                    time_analysis['completed_entries'] += 1
                    arrival = datetime.fromisoformat(log['arrival'])
                    departure = datetime.fromisoformat(log['departure'])
                    time_analysis['average_duration'] += (departure - arrival)

        if time_analysis['completed_entries'] > 0:
            time_analysis['average_duration'] = str(
                time_analysis['average_duration'] / time_analysis['completed_entries']
            )

        # Daily Statistics
        daily_stats = []
        current_date = start_date
        while current_date <= end_date:
            day_records = db.query(models.FinalRecords).filter(
                models.FinalRecords.entry_date == current_date.date(),
                *base_filters
            ).all()

            daily_entry_count = sum(len(record.time_logs) for record in day_records)
            daily_stats.append({
                'date': current_date.date().isoformat(),
                'total_entries': daily_entry_count,
                'unique_users': len(set(record.user_id for record in day_records))
            })
            current_date += timedelta(days=1)

        # Verification Statistics
        verification_stats = {
            'face_verified': 0,
            'qr_verified': 0,
            'both_verified': 0,
            'total_entries': 0
        }

        for record in db.query(models.FinalRecords).filter(*base_filters).all():
            for log in record.time_logs:
                verification_stats['total_entries'] += 1
                if log.get('face_verified'):
                    verification_stats['face_verified'] += 1
                if log.get('qr_verified'):
                    verification_stats['qr_verified'] += 1
                if log.get('face_verified') and log.get('qr_verified'):
                    verification_stats['both_verified'] += 1

        # User Type Analysis
        user_type_stats = db.query(
            models.User.is_instructor,
            func.count(distinct(models.FinalRecords.user_id)).label('user_count'),
            func.count(models.FinalRecords.record_id).label('entry_count')
        ).join(
            models.FinalRecords,
            models.User.user_id == models.FinalRecords.user_id
        ).filter(*base_filters).group_by(
            models.User.is_instructor
        ).all()

        user_analysis = {
            'instructors': {
                'count': 0,
                'entries': 0
            },
            'students': {
                'count': 0,
                'entries': 0
            }
        }

        for is_instructor, user_count, entry_count in user_type_stats:
            if is_instructor:
                user_analysis['instructors']['count'] = user_count
                user_analysis['instructors']['entries'] = entry_count
            else:
                user_analysis['students']['count'] = user_count
                user_analysis['students']['entries'] = entry_count

        return {
            "time_range": {
                "start_date": start_date.date().isoformat(),
                "end_date": end_date.date().isoformat()
            },
            "general_statistics": {
                "total_unique_users": general_stats.total_unique_users,
                "total_active_days": general_stats.total_active_days,
                "average_users_per_day": round(general_stats.total_unique_users / general_stats.total_active_days, 2)
                if general_stats.total_active_days > 0 else 0
            },
            "entry_distribution": entry_distribution,
            "time_analysis": time_analysis,
            "daily_statistics": daily_stats,
            "verification_statistics": verification_stats,
            "user_type_analysis": user_analysis
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/analytics/user/{user_id}")
def get_user_analytics(
    user_id: int,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    db: Session = Depends(get_db)
):
    try:
        if not end_date:
            end_date = datetime.utcnow()
        if not start_date:
            start_date = end_date - timedelta(days=30)

        user_records = db.query(models.FinalRecords).filter(
            models.FinalRecords.user_id == user_id,
            models.FinalRecords.entry_date.between(start_date.date(), end_date.date())
        ).all()

        entry_patterns = {
            'total_entries': 0,
            'completed_entries': 0,
            'average_duration': timedelta(0),
            'entry_types': {
                'normal': 0,
                'bypass': 0,
                'group': 0
            },
            'verification_stats': {
                'face_verified': 0,
                'qr_verified': 0,
                'both_verified': 0
            }
        }

        daily_activity = {}

        for record in user_records:
            for log in record.time_logs:
                entry_patterns['total_entries'] += 1
                
                # Entry type counting
                entry_type = log.get('entry_type', 'normal')
                entry_patterns['entry_types'][entry_type] += 1
                
                # Verification counting
                if log.get('face_verified'):
                    entry_patterns['verification_stats']['face_verified'] += 1
                if log.get('qr_verified'):
                    entry_patterns['verification_stats']['qr_verified'] += 1
                if log.get('face_verified') and log.get('qr_verified'):
                    entry_patterns['verification_stats']['both_verified'] += 1
                
                # Duration calculation
                if log.get('departure'):
                    entry_patterns['completed_entries'] += 1
                    arrival = datetime.fromisoformat(log['arrival'])
                    departure = datetime.fromisoformat(log['departure'])
                    duration = departure - arrival
                    entry_patterns['average_duration'] += duration
                    
                    # Daily activity tracking
                    date_str = arrival.date().isoformat()
                    if date_str not in daily_activity:
                        daily_activity[date_str] = {
                            'entries': 0,
                            'total_duration': timedelta(0)
                        }
                    daily_activity[date_str]['entries'] += 1
                    daily_activity[date_str]['total_duration'] += duration

        if entry_patterns['completed_entries'] > 0:
            entry_patterns['average_duration'] = str(
                entry_patterns['average_duration'] / entry_patterns['completed_entries']
            )

        return {
            "user_id": user_id,
            "time_range": {
                "start_date": start_date.date().isoformat(),
                "end_date": end_date.date().isoformat()
            },
            "entry_patterns": entry_patterns,
            "daily_activity": daily_activity
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/analytics/detailed")
def get_detailed_analytics(
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    institution_id: Optional[int] = None,
    db: Session = Depends(get_db)
):
    try:
        if not end_date:
            end_date = datetime.utcnow()
        if not start_date:
            start_date = end_date - timedelta(days=30)

        base_filters = [
            models.FinalRecords.entry_date.between(start_date.date(), end_date.date())
        ]
        if institution_id:
            base_filters.append(models.User.institution_id == institution_id)

        # Initialize statistics containers
        hourly_stats = defaultdict(lambda: {
            'total_entries': 0,
            'successful_entries': 0,
            'failed_entries': 0,
            'bypass_entries': 0
        })
        
        daily_stats = defaultdict(lambda: {
            'total_entries': 0,
            'successful_entries': 0,
            'failed_entries': 0,
            'bypass_entries': 0,
            'unique_users': set()
        })

        verification_stats = {
            'total_attempts': 0,
            'successful_verifications': 0,
            'failed_verifications': 0,
            'face_verification_failures': 0,
            'qr_verification_failures': 0
        }

        entry_stats = {
            'total_entries': 0,
            'normal_entries': 0,
            'bypass_entries': 0,
            'group_entries': 0,
            'completed_entries': 0,
            'incomplete_entries': 0
        }

        peak_hour_data = defaultdict(int)
        duration_stats = []
        
        # Process records
        records = db.query(models.FinalRecords).filter(*base_filters).all()
        for record in records:
            for log in record.time_logs:
                entry_stats['total_entries'] += 1
                arrival_time = datetime.fromisoformat(log['arrival'])
                hour = arrival_time.hour
                date_str = arrival_time.date().isoformat()

                # Hourly statistics
                hourly_stats[hour]['total_entries'] += 1
                peak_hour_data[hour] += 1

                # Daily statistics
                daily_stats[date_str]['total_entries'] += 1
                daily_stats[date_str]['unique_users'].add(record.user_id)

                # Entry type tracking
                entry_type = log.get('entry_type', 'normal')
                if entry_type == 'normal':
                    entry_stats['normal_entries'] += 1
                elif entry_type == 'bypass':
                    entry_stats['bypass_entries'] += 1
                    hourly_stats[hour]['bypass_entries'] += 1
                    daily_stats[date_str]['bypass_entries'] += 1

                if log.get('group_entry'):
                    entry_stats['group_entries'] += 1

                # Verification tracking
                verification_stats['total_attempts'] += 1
                is_successful = True

                if not log.get('face_verified'):
                    verification_stats['face_verification_failures'] += 1
                    is_successful = False

                if not log.get('qr_verified'):
                    verification_stats['qr_verification_failures'] += 1
                    is_successful = False

                if is_successful:
                    verification_stats['successful_verifications'] += 1
                    hourly_stats[hour]['successful_entries'] += 1
                    daily_stats[date_str]['successful_entries'] += 1
                else:
                    verification_stats['failed_verifications'] += 1
                    hourly_stats[hour]['failed_entries'] += 1
                    daily_stats[date_str]['failed_entries'] += 1

                # Duration tracking
                if log.get('departure'):
                    entry_stats['completed_entries'] += 1
                    arrival = datetime.fromisoformat(log['arrival'])
                    departure = datetime.fromisoformat(log['departure'])
                    duration_stats.append((departure - arrival).total_seconds())
                else:
                    entry_stats['incomplete_entries'] += 1

        # Calculate peak hours
        peak_hours = []
        if peak_hour_data:
            max_entries = max(peak_hour_data.values())
            peak_hours = [
                get_hour_range(hour) 
                for hour, count in peak_hour_data.items() 
                if count >= max_entries * 0.8  # Consider hours with at least 80% of max traffic
            ]

        # Calculate success rates
        success_rate = (
            (verification_stats['successful_verifications'] / verification_stats['total_attempts'] * 100)
            if verification_stats['total_attempts'] > 0 else 0
        )
        
        bypass_rate = (
            (entry_stats['bypass_entries'] / entry_stats['total_entries'] * 100)
            if entry_stats['total_entries'] > 0 else 0
        )

        # Calculate average duration
        avg_duration = (
            sum(duration_stats) / len(duration_stats)
            if duration_stats else 0
        )

        return {
            "time_range": {
                "start_date": start_date.date().isoformat(),
                "end_date": end_date.date().isoformat()
            },
            "peak_hours_analysis": {
                "peak_hours": peak_hours,
                "hourly_distribution": {
                    get_hour_range(hour): stats 
                    for hour, stats in hourly_stats.items()
                }
            },
            "success_metrics": {
                "overall_success_rate": round(success_rate, 2),
                "bypass_rate": round(bypass_rate, 2),
                "completion_rate": round(
                    entry_stats['completed_entries'] / entry_stats['total_entries'] * 100
                    if entry_stats['total_entries'] > 0 else 0, 2
                )
            },
            "verification_statistics": {
                **verification_stats,
                "face_verification_success_rate": round(
                    (1 - verification_stats['face_verification_failures'] / verification_stats['total_attempts']) * 100
                    if verification_stats['total_attempts'] > 0 else 0, 2
                ),
                "qr_verification_success_rate": round(
                    (1 - verification_stats['qr_verification_failures'] / verification_stats['total_attempts']) * 100
                    if verification_stats['total_attempts'] > 0 else 0, 2
                )
            },
            "entry_patterns": {
                **entry_stats,
                "average_duration_seconds": round(avg_duration, 2),
                "daily_patterns": {
                    date: {
                        **stats,
                        "unique_users": len(stats["unique_users"])
                    }
                    for date, stats in daily_stats.items()
                }
            },
            "efficiency_metrics": {
                "average_entries_per_day": round(
                    entry_stats['total_entries'] / len(daily_stats)
                    if daily_stats else 0, 2
                ),
                "average_duration_per_entry_seconds": round(avg_duration, 2),
                "bypass_to_normal_ratio": round(
                    entry_stats['bypass_entries'] / entry_stats['normal_entries']
                    if entry_stats['normal_entries'] > 0 else 0, 2
                )
            }
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/analytics/trends")
def get_trend_analytics(
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    institution_id: Optional[int] = None,
    db: Session = Depends(get_db)
):
    try:
        if not end_date:
            end_date = datetime.utcnow()
        if not start_date:
            start_date = end_date - timedelta(days=30)

        # Weekly trends
        weekly_stats = defaultdict(lambda: {
            'total_entries': 0,
            'successful_entries': 0,
            'unique_users': set(),
            'bypass_count': 0,
            'average_duration': []
        })

        # Process records for weekly trends
        records = db.query(models.FinalRecords).filter(
            models.FinalRecords.entry_date.between(start_date.date(), end_date.date())
        ).all()

        for record in records:
            for log in record.time_logs:
                arrival_time = datetime.fromisoformat(log['arrival'])
                week_number = arrival_time.isocalendar()[1]
                
                weekly_stats[week_number]['total_entries'] += 1
                weekly_stats[week_number]['unique_users'].add(record.user_id)
                
                if log.get('entry_type') == 'bypass':
                    weekly_stats[week_number]['bypass_count'] += 1
                
                if log.get('face_verified') and log.get('qr_verified'):
                    weekly_stats[week_number]['successful_entries'] += 1
                
                if log.get('departure'):
                    departure_time = datetime.fromisoformat(log['departure'])
                    duration = (departure_time - arrival_time).total_seconds()
                    weekly_stats[week_number]['average_duration'].append(duration)

        # Process weekly stats
        trend_analysis = {
            week: {
                'total_entries': stats['total_entries'],
                'successful_entries': stats['successful_entries'],
                'unique_users': len(stats['unique_users']),
                'bypass_rate': round(stats['bypass_count'] / stats['total_entries'] * 100, 2) if stats['total_entries'] > 0 else 0,
                'average_duration_seconds': round(sum(stats['average_duration']) / len(stats['average_duration']), 2) if stats['average_duration'] else 0
            }
            for week, stats in weekly_stats.items()
        }

        return {
            "time_range": {
                "start_date": start_date.date().isoformat(),
                "end_date": end_date.date().isoformat()
            },
            "weekly_trends": trend_analysis,
            "trend_indicators": {
                "growth_rate": calculate_growth_rate(trend_analysis),
                "peak_week": max(trend_analysis.items(), key=lambda x: x[1]['total_entries'])[0] if trend_analysis else None,
                "efficiency_trend": calculate_efficiency_trend(trend_analysis)
            }
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

def calculate_growth_rate(trend_data):
    if not trend_data or len(trend_data) < 2:
        return 0
    
    weeks = sorted(trend_data.keys())
    first_week = trend_data[weeks[0]]['total_entries']
    last_week = trend_data[weeks[-1]]['total_entries']
    
    return round(((last_week - first_week) / first_week * 100), 2) if first_week > 0 else 0

def calculate_efficiency_trend(trend_data):
    if not trend_data:
        return "No data available"
    
    success_rates = [
        stats['successful_entries'] / stats['total_entries'] * 100 if stats['total_entries'] > 0 else 0
        for stats in trend_data.values()
    ]
    
    avg_success_rate = sum(success_rates) / len(success_rates) if success_rates else 0
    
    if avg_success_rate >= 90:
        return "Excellent"
    elif avg_success_rate >= 75:
        return "Good"
    elif avg_success_rate >= 60:
        return "Fair"
    else:
        return "Needs Improvement" 