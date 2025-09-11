import logging
import logging.handlers
import os
import asyncio
import signal
import json
import csv
from datetime import datetime
from threading import Lock
from typing import Optional, Dict, Any, List
import atexit
from collections import deque
import time
import psutil

# ============================================================================
# Configuration
# ============================================================================

class LoggerConfig:
    def __init__(self):
        # Directory setup
        self.log_dir = os.path.join(os.getcwd(), "log")
        self.csv_dir = os.path.join(os.getcwd(), "csv")
        self.metrics_dir = os.path.join(os.getcwd(), "metrics")
        
        # Dynamic sizing based on system memory
        available_memory_gb = psutil.virtual_memory().available / (1024**3)
        base_queue_size = min(int(available_memory_gb * 2000), 25000)
        
        # Core settings
        self.queue_maxsize = int(os.getenv("LOG_QUEUE_SIZE", str(base_queue_size)))
        self.flush_timeout = float(os.getenv("LOG_FLUSH_TIMEOUT", "2.0"))
        self.worker_timeout = float(os.getenv("LOG_WORKER_TIMEOUT", "0.05"))
        self.batch_size = int(os.getenv("LOG_BATCH_SIZE", "10"))
        self.metrics_interval = int(os.getenv("LOG_METRICS_INTERVAL", "10000"))
        
        # Feature flags
        self.enable_structured_logging = os.getenv("LOG_STRUCTURED", "false").lower() == "true"
        self.enable_metrics_export = os.getenv("LOG_METRICS_EXPORT", "true").lower() == "true"
        self.enable_batch_processing = os.getenv("LOG_BATCH_MODE", "true").lower() == "true"
        
        # Strategy-specific log levels
        self.strategy_log_levels = {
            "STRA_1": getattr(logging, os.getenv("STRA_1_LOG_LEVEL", "INFO").upper()),
            "STRA_2": getattr(logging, os.getenv("STRA_2_LOG_LEVEL", "INFO").upper()),
            "default": getattr(logging, os.getenv("LOG_LEVEL", "INFO").upper())
        }
        
        # Create directories
        for dir_path in [self.log_dir, self.csv_dir, self.metrics_dir]:
            os.makedirs(dir_path, exist_ok=True)

config = LoggerConfig()

# ============================================================================
# Metrics System
# ============================================================================

class LogMetrics:
    def __init__(self):
        # Core counters
        self.logs_processed = 0
        self.logs_dropped = 0
        self.worker_errors = 0
        self.flush_timeouts = 0
        self.cross_thread_calls = 0
        self.batch_operations = 0
        self.json_validation_errors = 0
        self.dynamic_level_changes = 0
        
        # Performance tracking
        self.start_time = time.time()
        self.last_metrics_log = 0
        self.last_csv_export = 0
        self.avg_batch_size = 0.0
        self.max_queue_size = 0
        self.worker_cpu_time = 0.0
    
    def update_batch_stats(self, batch_size: int):
        self.batch_operations += 1
        self.avg_batch_size = ((self.avg_batch_size * (self.batch_operations - 1)) + batch_size) / self.batch_operations
    
    def should_log_metrics(self) -> bool:
        return (self.logs_processed - self.last_metrics_log) >= config.metrics_interval
    
    def should_export_csv(self) -> bool:
        return config.enable_metrics_export and (time.time() - self.last_csv_export) >= 300
    
    def to_dict(self) -> Dict[str, Any]:
        uptime = time.time() - self.start_time
        return {
            "logs_processed": self.logs_processed,
            "logs_dropped": self.logs_dropped,
            "worker_errors": self.worker_errors,
            "flush_timeouts": self.flush_timeouts,
            "cross_thread_calls": self.cross_thread_calls,
            "batch_operations": self.batch_operations,
            "json_validation_errors": self.json_validation_errors,
            "dynamic_level_changes": self.dynamic_level_changes,
            "avg_batch_size": round(self.avg_batch_size, 2),
            "max_queue_size": self.max_queue_size,
            "uptime_hours": round(uptime / 3600, 2),
            "logs_per_second": round(self.logs_processed / max(uptime, 1), 2),
            "error_rate_pct": round((self.worker_errors / max(self.logs_processed, 1)) * 100, 4)
        }
    
    def export_to_csv(self):
        if not config.enable_metrics_export:
            return
            
        csv_file = os.path.join(config.metrics_dir, f"log_metrics_{datetime.now().strftime('%Y-%m-%d')}.csv")
        metrics_data = self.to_dict()
        metrics_data["timestamp"] = datetime.now().isoformat()
        
        file_exists = os.path.isfile(csv_file)
        with open(csv_file, 'a', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=metrics_data.keys())
            if not file_exists:
                writer.writeheader()
            writer.writerow(metrics_data)
        
        self.last_csv_export = time.time()

metrics = LogMetrics()

# ============================================================================
# Formatters
# ============================================================================

def validate_json_log(log_entry: Dict[str, Any]) -> bool:
    """Basic validation for structured logs"""
    if not config.enable_structured_logging:
        return True
    
    required_fields = ["timestamp", "level", "message"]
    try:
        return all(field in log_entry for field in required_fields)
    except Exception:
        metrics.json_validation_errors += 1
        return False

class StructuredFormatter(logging.Formatter):
    """High-performance JSON structured logging"""
    def format(self, record):
        log_entry = {
            "timestamp": datetime.fromtimestamp(record.created).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
            "thread_id": record.thread
        }
        
        # Add trading context if available
        for attr in ['strategy_id', 'order_id', 'symbol', 'trade_no']:
            if hasattr(record, attr):
                log_entry[attr] = getattr(record, attr)
        
        if validate_json_log(log_entry):
            return json.dumps(log_entry)
        else:
            return f"{log_entry['timestamp']} [{log_entry['level']}] {log_entry['message']}"

class TradingFormatter(logging.Formatter):
    """Fast formatter for HFT systems"""
    def __init__(self):
        super().__init__('[%(asctime)s.%(msecs)03d] [%(levelname)s] [%(name)s] %(message)s', '%H:%M:%S')

# ============================================================================
# Async Logging Handler
# ============================================================================

class AsyncLoggingHandler(logging.Handler):
    """High-performance async logging handler with batch processing and metrics"""
    
    _instance: Optional['AsyncLoggingHandler'] = None
    _instance_lock = Lock()
    
    def __new__(cls, *args, **kwargs):
        with cls._instance_lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
            return cls._instance
    
    def __init__(self):
        if hasattr(self, '_initialized'):
            return
            
        super().__init__()
        self.queue: Optional[asyncio.Queue] = None
        self._worker_task: Optional[asyncio.Task] = None
        self._shutdown_event: Optional[asyncio.Event] = None
        self._worker_started = False
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._recent_errors = deque(maxlen=50)
        self._initialized = True
        
        atexit.register(self._cleanup_sync)
        self._setup_signal_handlers()
    
    def set_strategy_log_level(self, strategy_id: str, level: int):
        """Dynamically change log level for specific strategy"""
        config.strategy_log_levels[strategy_id] = level
        metrics.dynamic_level_changes += 1
        self._log_to_stderr(f"Changed log level for {strategy_id} to {logging.getLevelName(level)}")
    
    def emit(self, record: logging.LogRecord) -> None:
        """Optimized emit with dynamic level filtering"""
        # Strategy-specific level filtering
        strategy_id = getattr(record, 'strategy_id', 'default')
        required_level = config.strategy_log_levels.get(strategy_id, config.strategy_log_levels['default'])
        
        if record.levelno < required_level:
            return
        
        try:
            current_loop = asyncio.get_running_loop()
            
            if not self._worker_started or self._loop != current_loop:
                self._initialize_for_loop(current_loop)
            
            # Track queue usage
            current_queue_size = self.queue.qsize()
            metrics.max_queue_size = max(metrics.max_queue_size, current_queue_size)
            
            if current_queue_size > (config.queue_maxsize * 0.8):
                self._log_to_stderr(f"Queue size warning: {current_queue_size}/{config.queue_maxsize}")
            
            try:
                self.queue.put_nowait(record)
            except asyncio.QueueFull:
                metrics.logs_dropped += 1
                # Drop old records to make space
                try:
                    for _ in range(min(5, self.queue.qsize())):
                        self.queue.get_nowait()
                    self.queue.put_nowait(record)
                except asyncio.QueueEmpty:
                    pass
                    
        except RuntimeError:
            metrics.cross_thread_calls += 1
            self._handle_cross_thread_logging(record)
    
    def _initialize_for_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        """Initialize worker for current event loop"""
        if self._loop != loop or not self._worker_started:
            self._loop = loop
            self.queue = asyncio.Queue(maxsize=config.queue_maxsize)
            self._shutdown_event = asyncio.Event()
            
            if config.enable_batch_processing:
                self._worker_task = loop.create_task(self._batch_worker())
            else:
                self._worker_task = loop.create_task(self._single_worker())
            
            self._worker_started = True
            self._log_to_stderr(f"Logger initialized: batch_mode={config.enable_batch_processing}, queue_size={config.queue_maxsize}")
    
    async def _batch_worker(self) -> None:
        """Batch processing worker for high throughput"""
        batch_buffer = []
        last_flush = time.time()
        
        while not self._shutdown_event.is_set():
            try:
                try:
                    record = await asyncio.wait_for(self.queue.get(), timeout=config.worker_timeout)
                    batch_buffer.append(record)
                    
                    # Flush conditions
                    should_flush = (
                        len(batch_buffer) >= config.batch_size or
                        (time.time() - last_flush) > 0.1
                    )
                    
                    if should_flush:
                        await self._process_batch(batch_buffer)
                        metrics.update_batch_stats(len(batch_buffer))
                        batch_buffer.clear()
                        last_flush = time.time()
                        
                except asyncio.TimeoutError:
                    if batch_buffer:
                        await self._process_batch(batch_buffer)
                        metrics.update_batch_stats(len(batch_buffer))
                        batch_buffer.clear()
                        last_flush = time.time()
                    
                    # Periodic maintenance
                    if metrics.should_log_metrics():
                        self._log_metrics_summary()
                    if metrics.should_export_csv():
                        metrics.export_to_csv()
                    
                    continue
                    
            except asyncio.CancelledError:
                if batch_buffer:
                    await self._process_batch(batch_buffer)
                break
            except Exception as e:
                metrics.worker_errors += 1
                self._recent_errors.append(f"{datetime.now().isoformat()}: {str(e)}")
                self._log_to_stderr(f"Batch worker error: {e}")
                await asyncio.sleep(0.01)
    
    async def _process_batch(self, batch: List[logging.LogRecord]) -> None:
        """Process batch of log records efficiently"""
        start_time = time.time()
        
        try:
            for record in batch:
                file_handler.handle(record)
                console_handler.handle(record)
                metrics.logs_processed += 1
                self.queue.task_done()
        except Exception as e:
            self._log_to_stderr(f"Batch processing error: {e}")
        
        metrics.worker_cpu_time += (time.time() - start_time)
    
    async def _single_worker(self) -> None:
        """Single record processing for lower latency"""
        while not self._shutdown_event.is_set():
            try:
                record = await asyncio.wait_for(self.queue.get(), timeout=config.worker_timeout)
                
                file_handler.handle(record)
                console_handler.handle(record)
                
                metrics.logs_processed += 1
                self.queue.task_done()
                
                # Periodic maintenance
                if metrics.should_log_metrics():
                    self._log_metrics_summary()
                if metrics.should_export_csv():
                    metrics.export_to_csv()
                    
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break
            except Exception as e:
                metrics.worker_errors += 1
                self._recent_errors.append(f"{datetime.now().isoformat()}: {str(e)}")
                self._log_to_stderr(f"Single worker error: {e}")
    
    def _log_metrics_summary(self):
        """Log periodic metrics summary"""
        metrics_summary = metrics.to_dict()
        self._log_to_stderr(f"[METRICS] {json.dumps(metrics_summary)}")
        metrics.last_metrics_log = metrics.logs_processed
    
    def get_performance_stats(self) -> Dict[str, Any]:
        """Get detailed performance statistics"""
        return {
            **metrics.to_dict(),
            "queue_size": self.queue.qsize() if self.queue else 0,
            "queue_utilization_pct": round((self.queue.qsize() / config.queue_maxsize) * 100, 2) if self.queue else 0,
            "worker_running": self._worker_started,
            "batch_mode": config.enable_batch_processing,
            "avg_worker_cpu_ms": round(metrics.worker_cpu_time * 1000, 2),
            "recent_errors": list(self._recent_errors)[-10:],
            "config": {
                "queue_maxsize": config.queue_maxsize,
                "batch_size": config.batch_size,
                "worker_timeout": config.worker_timeout
            }
        }
    
    def _setup_signal_handlers(self):
        """Setup graceful shutdown signal handlers"""
        try:
            signal.signal(signal.SIGINT, self._signal_handler)
            signal.signal(signal.SIGTERM, self._signal_handler)
        except (OSError, ValueError):
            pass
    
    def _signal_handler(self, signum, frame):
        print(f"[Logger] Signal {signum} received, exporting final metrics...")
        metrics.export_to_csv()
        self.close()
    
    def _handle_cross_thread_logging(self, record: logging.LogRecord) -> None:
        """Handle logging from different threads"""
        try:
            if self._loop and self._loop.is_running():
                asyncio.run_coroutine_threadsafe(self._async_emit(record), self._loop)
            else:
                self._direct_emit(record)
        except Exception as e:
            self._log_to_stderr(f"Cross-thread error: {e}")
            self._direct_emit(record)
    
    async def _async_emit(self, record: logging.LogRecord) -> None:
        """Async emit for cross-thread calls"""
        try:
            await asyncio.wait_for(self.queue.put(record), timeout=0.05)
        except asyncio.TimeoutError:
            metrics.logs_dropped += 1
            self._direct_emit(record)
    
    def _direct_emit(self, record: logging.LogRecord) -> None:
        """Direct emit bypassing queue"""
        try:
            file_handler.handle(record)
            console_handler.handle(record)
            metrics.logs_processed += 1
        except Exception as e:
            self._log_to_stderr(f"Direct emit error: {e}")
    
    def _log_to_stderr(self, message: str) -> None:
        """Internal logging to stderr"""
        import sys
        timestamp = datetime.now().strftime('%H:%M:%S.%f')[:-3]
        sys.stderr.write(f"[{timestamp}] [LOGGER] {message}\n")
        sys.stderr.flush()
    
    async def flush_async(self, timeout: float = None) -> Dict[str, Any]:
        """Async flush with timeout"""
        if timeout is None:
            timeout = config.flush_timeout
        
        if not self._worker_started or not self.queue:
            return {"status": "not_started"}
        
        pending = self.queue.qsize()
        start_time = time.time()
        
        try:
            await asyncio.wait_for(self.queue.join(), timeout=timeout)
            return {
                "status": "success",
                "pending_logs": pending,
                "flush_time_ms": int((time.time() - start_time) * 1000),
                "final_metrics": metrics.to_dict()
            }
        except asyncio.TimeoutError:
            metrics.flush_timeouts += 1
            return {
                "status": "timeout",
                "pending_logs": pending,
                "remaining_logs": self.queue.qsize()
            }
    
    def flush_sync(self, timeout: float = None) -> Dict[str, Any]:
        """Synchronous flush"""
        if not self._loop or not self._loop.is_running():
            return {"status": "no_loop"}
        
        try:
            future = asyncio.run_coroutine_threadsafe(self.flush_async(timeout), self._loop)
            return future.result(timeout=timeout or config.flush_timeout)
        except Exception as e:
            return {"status": "error", "error": str(e)}
    
    def close(self) -> Dict[str, Any]:
        """Close handler with cleanup"""
        try:
            if self._shutdown_event:
                self._shutdown_event.set()
            
            # Final metrics export
            metrics.export_to_csv()
            
            flush_result = self.flush_sync(timeout=config.flush_timeout)
            
            if self._worker_task and not self._worker_task.done():
                self._worker_task.cancel()
            
            self._worker_started = False
            return {"status": "closed", "final_stats": self.get_performance_stats()}
            
        except Exception as e:
            return {"status": "error", "error": str(e)}
        finally:
            super().close()
    
    def _cleanup_sync(self):
        """Synchronous cleanup for atexit"""
        result = self.close()
        self._log_to_stderr(f"Logger shutdown: {result.get('status', 'unknown')}")

# ============================================================================
# Handler Setup
# ============================================================================

def setup_handlers():
    """Create and configure file and console handlers"""
    today_str = datetime.now().strftime("%Y-%m-%d")
    
    # File handler with rotation
    if hasattr(logging.handlers, 'TimedRotatingFileHandler'):
        file_handler = logging.handlers.TimedRotatingFileHandler(
            filename=os.path.join(config.log_dir, "hft_strategy.log"),
            when='midnight', interval=1, backupCount=7, encoding='utf-8'
        )
    else:
        log_file = os.path.join(config.log_dir, f"hft_strategy_{today_str}.log")
        file_handler = logging.FileHandler(log_file, mode='a', encoding='utf-8')
    
    console_handler = logging.StreamHandler()
    
    # Choose formatter based on configuration
    if config.enable_structured_logging:
        formatter = StructuredFormatter()
    else:
        formatter = TradingFormatter()
    
    file_handler.setFormatter(formatter)
    console_handler.setFormatter(formatter)
    file_handler.setLevel(logging.INFO)
    console_handler.setLevel(logging.INFO)
    
    return file_handler, console_handler

file_handler, console_handler = setup_handlers()

# ============================================================================
# Logger Factory
# ============================================================================

class TradingLoggerAdapter(logging.LoggerAdapter):
    """Logger adapter with trading context"""
    def __init__(self, logger, extra, strategy_id=None):
        super().__init__(logger, extra)
        self.strategy_id = strategy_id
    
    def process(self, msg, kwargs):
        extra = kwargs.get('extra', {})
        if self.strategy_id:
            extra['strategy_id'] = self.strategy_id
        kwargs['extra'] = extra
        return msg, kwargs

def get_logger(name: str, strategy_id: str = None) -> logging.Logger:
    """Get optimized logger for trading applications"""
    logger = logging.getLogger(name)
    
    # Set strategy-specific log level
    if strategy_id:
        level = config.strategy_log_levels.get(strategy_id, config.strategy_log_levels['default'])
        logger.setLevel(level)
    else:
        logger.setLevel(config.strategy_log_levels['default'])
    
    logger.propagate = False
    
    # Add async handler if not already present
    if not any(isinstance(h, AsyncLoggingHandler) for h in logger.handlers):
        logger.addHandler(async_handler)
    
    # Return adapter for strategy loggers
    if strategy_id:
        return TradingLoggerAdapter(logger, {}, strategy_id=strategy_id)
    
    return logger

# ============================================================================
# Global Setup & Shutdown
# ============================================================================

async_handler = AsyncLoggingHandler()
logger = get_logger(__name__)

def shutdown_logger(timeout: float = None, export_final_metrics: bool = True) -> Dict[str, Any]:
    """Shutdown logger with performance stats export"""
    if timeout is None:
        timeout = config.flush_timeout
    
    print(f"[Logger] Shutting down (timeout={timeout}s)...")
    
    # Get final performance stats
    final_stats = async_handler.get_performance_stats()
    
    # Export final metrics
    if export_final_metrics and config.enable_metrics_export:
        try:
            metrics.export_to_csv()
            print(f"[Logger] Final metrics exported to {config.metrics_dir}")
        except Exception as e:
            print(f"[Logger] Metrics export error: {e}")
    
    # Shutdown logger
    result = async_handler.close()
    
    # Print performance summary
    if 'final_stats' in result:
        stats = final_stats
        print(f"[Logger] Performance Summary:")
        print(f"  • Processed: {stats['logs_processed']:,} logs")
        print(f"  • Dropped: {stats['logs_dropped']:,} logs ({stats['error_rate_pct']}%)")
        print(f"  • Avg throughput: {stats['logs_per_second']:.1f} logs/sec")
        print(f"  • Queue utilization: {stats['queue_utilization_pct']:.1f}%")
        if config.enable_batch_processing:
            print(f"  • Avg batch size: {stats['avg_batch_size']:.1f}")
    
    return {**result, "performance_stats": final_stats}

# ============================================================================
# Public Interface
# ============================================================================

__all__ = [
    'logger', 
    'get_logger', 
    'shutdown_logger',
    'async_handler',
    'metrics',
    'config'
]
