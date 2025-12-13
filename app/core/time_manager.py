from datetime import datetime, time
import logging

try:
    from chinese_calendar import is_workday, is_holiday
    HAS_CHINESE_CALENDAR = True
except ImportError:
    HAS_CHINESE_CALENDAR = False

logger = logging.getLogger(__name__)

class TimeManager:
    @staticmethod
    def is_trading_day(date_obj: datetime = None) -> bool:
        """
        Check if the given date is a trading day.
        Defaults to today if date_obj is None.
        """
        if date_obj is None:
            date_obj = datetime.now()
            
        # Basic check: Weekend
        if date_obj.weekday() >= 5: # 5=Saturday, 6=Sunday
            # However, sometimes weekends are workdays in China, but stock market is usually closed on weekends regardless of "workday" status for other sectors?
            # Actually, Chinese stock market is ALWAYS closed on Sat/Sun.
            # Even if it is a "make-up workday", stock market is closed.
            return False

        if HAS_CHINESE_CALENDAR:
            # is_holiday returns True for weekends and public holidays
            # But we already checked weekends.
            # chinese_calendar.is_holiday() returns True for holidays.
            # Note: chinese_calendar.is_workday() returns True for make-up workdays (Sat/Sun).
            # Stock market: Closed on Public Holidays and Weekends.
            # So if it is a holiday, it is closed.
            if is_holiday(date_obj):
                return False
        
        return True

    @staticmethod
    def is_trading_time(dt: datetime = None) -> bool:
        """
        Check if it is currently trading time (including call auction).
        9:15 - 11:30, 13:00 - 15:00
        """
        if dt is None:
            dt = datetime.now()

        if not TimeManager.is_trading_day(dt):
            return False

        current_time = dt.time()
        
        # Morning session (including call auction 9:15-9:25)
        morning_start = time(9, 15)
        morning_end = time(11, 30)
        
        # Afternoon session
        afternoon_start = time(13, 0)
        afternoon_end = time(15, 0)

        if (morning_start <= current_time <= morning_end) or \
           (afternoon_start <= current_time <= afternoon_end):
            return True
            
        return False

    @staticmethod
    def get_market_status_message() -> str:
        now = datetime.now()
        if not TimeManager.is_trading_day(now):
            return "休市 (非交易日)"
        
        if TimeManager.is_trading_time(now):
            return "交易中"
            
        # Check specific intervals
        t = now.time()
        if t < time(9, 15):
            return "盘前"
        elif time(11, 30) < t < time(13, 0):
            return "午休"
        elif t > time(15, 0):
            return "盘后"
            
        return "休市"
