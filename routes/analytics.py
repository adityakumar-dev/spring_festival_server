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
            'hourly_stats': defaultdict(int),
            'verification_stats': {
                'total_attempts': 0,
                'face_success': 0,
                'qr_success': 0,
                'both_success': 0,
                'group_success': 0,
                'failures': 0
            },
            'entry_types': defaultdict(int),
            'daily_stats': defaultdict(lambda: {
                'entries': 0,
                'successes': 0,
                'unique_users': set(),
                'group_entries': 0,
                'group_successes': 0
            }),
            'completion_times': [],
            'duration_stats': [],
            'ongoing_users': []
        }

        # Process records
        records = db.query(models.FinalRecords).filter(*base_filters).order_by(
            models.FinalRecords.entry_date.desc()
        ).all()

        for record in records:
            for log in record.time_logs:
                # Basic time processing
                arrival_time = convert_to_system_time(datetime.fromisoformat(log['arrival']))
                hour = arrival_time.hour
                date_str = arrival_time.date().isoformat()

                # Track entry type
                entry_type = log.get('entry_type', 'normal')
                stats['entry_types'][entry_type] += 1

                # Track hourly distribution
                stats['hourly_stats'][hour] += 1

                # Process verification stats
                stats['verification_stats']['total_attempts'] += 1
                is_success = False

                # Debug prints
                print(f"\nProcessing entry:")
                print(f"Entry type: {entry_type}")
                print(f"Face verified: {log.get('face_verified')}")
                print(f"QR verified: {log.get('qr_verified')}")
                print(f"Instructor verified: {log.get('verified_by_instructor')}")

                # Check face verification - Include both direct face verification and instructor verification
                if log.get('face_verified') is True or (entry_type == 'group_entry' and log.get('verified_by_instructor') is True):
                    stats['verification_stats']['face_success'] += 1
                    print(f"Face verification counted. Total face success: {stats['verification_stats']['face_success']}")

                # Check QR verification
                if log.get('qr_verified') is True:
                    stats['verification_stats']['qr_success'] += 1
                    print(f"QR verification counted. Total QR success: {stats['verification_stats']['qr_success']}")

                # Determine overall success
                if entry_type == 'group_entry':
                    # Group entry is successful if verified by instructor OR face verified
                    if log.get('verified_by_instructor') is True or log.get('face_verified') is True:
                        is_success = True
                        stats['verification_stats']['group_success'] += 1
                        stats['verification_stats']['both_success'] += 1
                        print("Group entry success counted")
                else:
                    # Normal entry is successful if both face AND QR are verified
                    if log.get('face_verified') is True and log.get('qr_verified') is True:
                        is_success = True
                        stats['verification_stats']['both_success'] += 1
                        print("Normal entry success counted")

                # Update success counters
                if is_success:
                    stats['daily_stats'][date_str]['successes'] += 1
                    print(f"Success added to daily stats. Date: {date_str}")
                else:
                    stats['verification_stats']['failures'] += 1
                    print("Entry marked as failure")

                # Print running totals
                print(f"\nRunning totals:")
                print(f"Total attempts: {stats['verification_stats']['total_attempts']}")
                print(f"Face successes: {stats['verification_stats']['face_success']}")
                print(f"QR successes: {stats['verification_stats']['qr_success']}")
                print(f"Overall successes: {stats['verification_stats']['both_success']}")
                print(f"Group successes: {stats['verification_stats']['group_success']}")
                print(f"Failures: {stats['verification_stats']['failures']}")

                # Update daily statistics
                stats['daily_stats'][date_str]['entries'] += 1
                stats['daily_stats'][date_str]['unique_users'].add(record.user_id)
                if entry_type == 'group_entry':
                    stats['daily_stats'][date_str]['group_entries'] += 1

                # Calculate completion time with improved logic
                if log.get('arrival'):
                    arrival = datetime.fromisoformat(log['arrival'])
                    arrival_utc = convert_to_system_time(arrival)
                    
                    if entry_type == 'group_entry':
                        completion_time = 0.5  # Set default 30 seconds for group entries
                        verification_type = 'instructor' if log.get('verified_by_instructor') else 'normal'
                    else:
                        # For normal entries
                        if log.get('face_verification_time'):
                            verification_time = convert_to_system_time(
                                datetime.fromisoformat(log['face_verification_time'])
                            )
                            completion_time = (verification_time - arrival_utc).total_seconds() / 60
                        else:
                            completion_time = 1.0  # Set default 1 minute for normal entries
                        verification_type = 'normal'
                    
                    stats['completion_times'].append({
                        'time': round(completion_time, 2),
                        'date': arrival_utc.date().isoformat(),
                        'type': entry_type,
                        'verification_type': verification_type
                    })

                # Track ongoing users (no departure time)
                current_time = get_current_time()
                if log.get('arrival') and not log.get('departure'):
                    arrival_time = convert_to_system_time(datetime.fromisoformat(log['arrival']))
                    duration_so_far = (current_time - arrival_time).total_seconds() / 60
                    
                    stats['ongoing_users'].append({
                        'user_id': record.user_id,
                        'arrival_time': arrival_time.isoformat(),
                        'duration_so_far': round(duration_so_far, 2),
                        'entry_type': entry_type
                    })

                # Calculate duration if available
                if log.get('arrival') and log.get('departure'):
                    arrival = convert_to_system_time(datetime.fromisoformat(log['arrival']))
                    departure = convert_to_system_time(datetime.fromisoformat(log['departure']))
                    duration = (departure - arrival).total_seconds() / 60
                    if duration > 0:
                        stats['duration_stats'].append(duration)

        # Calculate derived metrics
        total_entries = stats['verification_stats']['total_attempts']
        total_success = stats['verification_stats']['both_success']
        total_group_entries = stats['entry_types'].get('group_entry', 0)
        group_success = stats['verification_stats'].get('group_success', 0)

        # Debug final calculations
        print(f"\nFinal calculations:")
        print(f"Total entries: {total_entries}")
        print(f"Total success: {total_success}")
        print(f"Success rate: {(total_success / total_entries * 100) if total_entries > 0 else 0}%")

        return {
            "time_range": {
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
                "timezone": "Asia/Kolkata (UTC+5:30)"
            },
            "traffic_analysis": {
                "peak_hours": [
                    get_hour_range(hour)
                    for hour, count in stats['hourly_stats'].items()
                    if count >= max(stats['hourly_stats'].values()) * 0.8
                ],
                "hourly_distribution": {
                    get_hour_range(hour): count
                    for hour, count in stats['hourly_stats'].items()
                },
                "busiest_periods": sorted(
                    [(get_hour_range(hour), count) 
                     for hour, count in stats['hourly_stats'].items()],
                    key=lambda x: x[1],
                    reverse=True
                )[:3]
            },
            "performance_metrics": {
                "success_rate": round(
                    (total_success / total_entries * 100)
                    if total_entries > 0 else 0, 2
                ),
                "face_verification_rate": round(
                    (stats['verification_stats']['face_success'] / total_entries * 100)
                    if total_entries > 0 else 0, 2
                ),
                "qr_verification_rate": round(
                    (stats['verification_stats']['qr_success'] / total_entries * 100)
                    if total_entries > 0 else 0, 2
                ),
                "group_success_rate": round(
                    (group_success / total_group_entries * 100)
                    if total_group_entries > 0 else 0, 2
                )
            },
            "scan_efficiency": {
                "average_completion_time_minutes": round(
                    sum(entry['time'] for entry in stats['completion_times']) / 
                    len(stats['completion_times'])
                    if stats['completion_times'] else 0, 2
                ),
                "recent_average_completion_time_minutes": round(
                    sum(entry['time'] for entry in stats['completion_times'][-10:]) / 
                    len(stats['completion_times'][-10:])
                    if stats['completion_times'][-10:] else 0, 2
                ),
                "recent_scans": [{
                    'time': entry['time'],
                    'date': entry['date'],
                    'type': entry['type'],
                    'verification_type': entry['verification_type']
                } for entry in stats['completion_times'][-10:]],
                "total_valid_scans": len(stats['completion_times']),
                "completion_rate": round(
                    (len(stats['completion_times']) / total_entries * 100)
                    if total_entries > 0 else 0, 2
                ),
                "completion_time_distribution": {
                    "under_1_minute": len([e for e in stats['completion_times'] if e['time'] <= 1]),
                    "1_to_2_minutes": len([e for e in stats['completion_times'] if 1 < e['time'] <= 2]),
                    "2_to_5_minutes": len([e for e in stats['completion_times'] if 2 < e['time'] <= 5])
                }
            },
            "entry_statistics": {
                "total_entries": total_entries,
                "entry_types": dict(stats['entry_types']),
                "average_duration_minutes": round(
                    sum(stats['duration_stats']) / len(stats['duration_stats'])
                    if stats['duration_stats'] else 0, 2
                ),
                "daily_patterns": {
                    date: {
                        "total_entries": data['entries'],
                        "successful_entries": data['successes'],
                        "unique_users": len(data['unique_users']),
                        "group_entries": data['group_entries'],
                        "success_rate": round(
                            (data['successes'] / data['entries'] * 100)
                            if data['entries'] > 0 else 0, 2
                        )
                    }
                    for date, data in stats['daily_stats'].items()
                },
                "ongoing_users": {
                    "count": len(stats['ongoing_users']),
                    "details": sorted(
                        stats['ongoing_users'],
                        key=lambda x: x['duration_so_far'],
                        reverse=True
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
            'total_entries': 0,
            'group_verifications': 0,
            'group_verification_success': 0,
            'instructor_verifications': 0,
            'instructor_led_entries': 0
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
                if log.get('entry_type') == 'group':
                    verification_stats['group_verifications'] += 1
                    if log.get('face_verified') and (log.get('verified_by_instructor') or log.get('face_verified')):
                        verification_stats['group_verification_success'] += 1
                    if log.get('verified_by_instructor'):
                        verification_stats['instructor_verifications'] += 1

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
            "verification_statistics": {
                **verification_stats,
                "group_verification_rate": round(
                    verification_stats['group_verification_success'] / 
                    verification_stats['group_verifications'] * 100
                    if verification_stats['group_verifications'] > 0 else 0, 2
                ),
                "instructor_led_percentage": round(
                    verification_stats['instructor_verifications'] / 
                    verification_stats['total_entries'] * 100
                    if verification_stats['total_entries'] > 0 else 0, 2
                )
            },
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
                if not isinstance(entry_type, str):
                    print(f"Warning: Invalid entry_type: {entry_type}")  # Debug print
                    entry_type = 'normal'  # Default to normal if invalid
                
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
                if not isinstance(entry_type, str):
                    print(f"Warning: Invalid entry_type: {entry_type}")  # Debug print
                    entry_type = 'normal'  # Default to normal if invalid
                
                if entry_type == 'normal':
                    entry_stats['normal_entries'] += 1
                elif entry_type == 'bypass':
                    entry_stats['bypass_entries'] += 1
                    hourly_stats[hour]['bypass_entries'] += 1
                    daily_stats[date_str]['bypass_entries'] += 1
                elif entry_type == 'group_entry':
                    entry_stats['group_entries'] += 1

                print(f"Current entry_stats: {entry_stats}")  # Debug print

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
            'average_duration': [],
            'group_entries': 0,
            'successful_group_entries': 0,
            'instructor_verifications': 0
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

                if log.get('entry_type') == 'group':
                    weekly_stats[week_number]['group_entries'] += 1
                    if log.get('face_verified') and (log.get('verified_by_instructor') or log.get('face_verified')):
                        weekly_stats[week_number]['successful_group_entries'] += 1
                    if log.get('verified_by_instructor'):
                        weekly_stats[week_number]['instructor_verifications'] += 1

        # Process weekly stats
        trend_analysis = {
            week: {
                'total_entries': stats['total_entries'],
                'successful_entries': stats['successful_entries'],
                'unique_users': len(stats['unique_users']),
                'bypass_rate': round(stats['bypass_count'] / stats['total_entries'] * 100, 2) if stats['total_entries'] > 0 else 0,
                'average_duration_seconds': round(sum(stats['average_duration']) / len(stats['average_duration']), 2) if stats['average_duration'] else 0,
                'group_entry_success_rate': round(
                    stats['successful_group_entries'] / stats['group_entries'] * 100
                    if stats['group_entries'] > 0 else 0, 2
                ),
                'instructor_verification_count': stats['instructor_verifications']
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
                "efficiency_trend": calculate_efficiency_trend(trend_analysis),
                "group_verification_trend": calculate_group_verification_trend(trend_analysis)
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

def calculate_group_verification_trend(trend_data):
    if not trend_data:
        return "No data available"
    
    success_rates = [
        stats['group_entry_success_rate']
        for stats in trend_data.values()
        if stats['group_entries'] > 0
    ]
    
    if not success_rates:
        return "No group entries recorded"
    
    avg_success_rate = sum(success_rates) / len(success_rates)
    
    if avg_success_rate >= 90:
        return "Excellent"
    elif avg_success_rate >= 75:
        return "Good"
    elif avg_success_rate >= 60:
        return "Fair"
    else:
        return "Needs Improvement" 