import os
import psutil
import time
import threading
import signal
import sys
import atexit
from datetime import datetime
from typing import Optional, Dict, Any
from utils.logger import logger

# Global variables for module-level interface
_monitor_thread = None
_stop_event = threading.Event()
_is_running = False
_signals_registered = False

# Default configuration
DEFAULT_CONFIG = {
    'interval': 2.0,
    'cpu_threshold': 80.0,
    'memory_threshold': 85.0,
    'disk_threshold': 90.0,
}

def _setup_signal_handlers():
    """Setup signal handlers for graceful shutdown"""
    global _signals_registered
    
    if _signals_registered:
        return
    
    def signal_handler(sig, frame):
        signal_name = signal.Signals(sig).name
        print(f"\nReceived {signal_name} signal. Shutting down monitor gracefully...")
        logger.info(f"Received {signal_name} signal, stopping monitor")
        stop()
        # Don't exit here, let the main application handle it
    
    # Register signal handlers
    try:
        signal.signal(signal.SIGINT, signal_handler)   # Ctrl+C
        signal.signal(signal.SIGTERM, signal_handler)  # Termination
        
        # Unix-only signals
        if hasattr(signal, 'SIGHUP'):
            signal.signal(signal.SIGHUP, signal_handler)   # Hangup
        if hasattr(signal, 'SIGQUIT'):
            signal.signal(signal.SIGQUIT, signal_handler)  # Quit
            
        _signals_registered = True
        logger.info("Signal handlers registered for graceful shutdown")
            
    except (OSError, ValueError) as e:
        # Some signals might not be available on all platforms
        logger.warning(f"Could not register some signal handlers: {e}")

def _get_metrics():
    """Get current system metrics"""
    try:
        cpu = psutil.cpu_percent(interval=0.1)
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage('/')
        
        metrics = {
            'cpu': round(cpu, 1),
            'memory': round(memory.percent, 1),
            'memory_gb': round(memory.used / (1024**3), 2),
            'memory_total_gb': round(memory.total / (1024**3), 2),
            'disk': round(disk.percent, 1),
            'disk_free_gb': round(disk.free / (1024**3), 2),
            'processes': len(psutil.pids())
        }
        
        # Add load average on Unix systems
        try:
            load_avg = os.getloadavg()
            metrics['load_1min'] = round(load_avg[0], 2)
        except (OSError, AttributeError):
            pass
            
        return metrics
        
    except Exception as e:
        logger.error(f"Failed to get metrics: {e}")
        return {}

def _check_thresholds(metrics):
    """Check and log threshold violations"""
    config = DEFAULT_CONFIG
    
    if metrics.get('cpu', 0) > config['cpu_threshold']:
        logger.warning(f"HIGH CPU USAGE: {metrics['cpu']}% (threshold: {config['cpu_threshold']}%)")
    
    if metrics.get('memory', 0) > config['memory_threshold']:
        logger.warning(f"HIGH MEMORY USAGE: {metrics['memory']}% (threshold: {config['memory_threshold']}%)")
    
    if metrics.get('disk', 0) > config['disk_threshold']:
        logger.warning(f"HIGH DISK USAGE: {metrics['disk']}% (threshold: {config['disk_threshold']}%)")

def _monitor_loop():
    """Main monitoring loop with error recovery"""
    global _stop_event
    
    logger.info(f"System monitoring started with {DEFAULT_CONFIG['interval']}s interval")
    consecutive_errors = 0
    max_consecutive_errors = 10
    
    while not _stop_event.is_set():
        try:
            metrics = _get_metrics()
            
            if metrics:
                # Build log message
                log_parts = [
                    f"CPU: {metrics['cpu']}%",
                    f"MEM: {metrics['memory']}% ({metrics['memory_gb']}/{metrics['memory_total_gb']}GB)",
                    f"DISK: {metrics['disk']}%",
                    f"PROC: {metrics['processes']}"
                ]
                
                if 'load_1min' in metrics:
                    log_parts.append(f"LOAD: {metrics['load_1min']}")
                
                logger.info(" | ".join(log_parts))
                _check_thresholds(metrics)
                
                # Reset error counter on successful iteration
                consecutive_errors = 0
            else:
                consecutive_errors += 1
                if consecutive_errors >= max_consecutive_errors:
                    logger.error(f"Too many consecutive errors ({consecutive_errors}), stopping monitor")
                    break
            
            _stop_event.wait(DEFAULT_CONFIG['interval'])
            
        except Exception as e:
            consecutive_errors += 1
            logger.error(f"Monitor loop error ({consecutive_errors}/{max_consecutive_errors}): {e}")
            
            if consecutive_errors >= max_consecutive_errors:
                logger.error("Maximum consecutive errors reached, stopping monitor")
                break
                
            _stop_event.wait(min(DEFAULT_CONFIG['interval'], 5.0))  # Cap error retry interval
    
    logger.info("System monitoring stopped")

def start(interval: float = 2.0, 
          cpu_threshold: float = 80.0,
          memory_threshold: float = 85.0,
          disk_threshold: float = 90.0,
          auto_signals: bool = True):
    """
    Start system monitoring with automatic signal handling
    
    Args:
        interval: Monitoring interval in seconds
        cpu_threshold: CPU usage threshold for warnings (%)
        memory_threshold: Memory usage threshold for warnings (%)
        disk_threshold: Disk usage threshold for warnings (%)
        auto_signals: Automatically setup signal handlers for graceful shutdown
    """
    global _monitor_thread, _stop_event, _is_running, DEFAULT_CONFIG
    
    if _is_running:
        print("System monitor is already running")
        logger.warning("Attempted to start monitor while already running")
        return
    
    # Update configuration
    DEFAULT_CONFIG.update({
        'interval': interval,
        'cpu_threshold': cpu_threshold,
        'memory_threshold': memory_threshold,
        'disk_threshold': disk_threshold
    })
    
    # Setup signal handlers for graceful shutdown
    if auto_signals:
        _setup_signal_handlers()
    
    # Start monitoring thread
    _stop_event.clear()
    _monitor_thread = threading.Thread(
        target=_monitor_loop,
        name="SystemMonitorDaemon",
        daemon=True
    )
    _monitor_thread.start()
    _is_running = True
    
    print(f"✓ System monitor started (interval: {interval}s)")
    logger.info(f"System monitor started with config: interval={interval}s, cpu_thresh={cpu_threshold}%, mem_thresh={memory_threshold}%, disk_thresh={disk_threshold}%")
    
    if auto_signals:
        print("✓ Signal handlers registered for graceful shutdown")

def stop(timeout: float = 3.0):
    """Stop system monitoring gracefully"""
    global _stop_event, _monitor_thread, _is_running
    
    if not _is_running:
        return
    
    print("Stopping system monitor...")
    logger.info("Stop requested, shutting down gracefully")
    
    _stop_event.set()
    
    if _monitor_thread and _monitor_thread.is_alive():
        _monitor_thread.join(timeout=timeout)
        if _monitor_thread.is_alive():
            print("Warning: Monitor thread did not stop within timeout")
            logger.warning(f"Monitor thread did not stop within {timeout}s timeout")
    
    _is_running = False
    print("✓ System monitor stopped")
    logger.info("System monitor stopped successfully")

def is_running():
    """Check if monitoring is active"""
    return _is_running

def get_metrics():
    """Get current system metrics without logging"""
    return _get_metrics()

def status():
    """Print current status and metrics"""
    if _is_running:
        metrics = get_metrics()
        print(f"Monitor Status: RUNNING (interval: {DEFAULT_CONFIG['interval']}s)")
        logger.debug(f"Monitor status check: RUNNING")
        
        if metrics:
            parts = [
                f"CPU: {metrics.get('cpu', 0)}%",
                f"MEM: {metrics.get('memory', 0)}%",
                f"DISK: {metrics.get('disk', 0)}%"
            ]
            if 'load_1min' in metrics:
                parts.append(f"LOAD: {metrics['load_1min']}")
            print(f"Current Metrics: {' | '.join(parts)}")
        else:
            print("Current Metrics: Unable to fetch")
            logger.warning("Unable to fetch metrics for status check")
    else:
        print("Monitor Status: STOPPED")
        logger.debug("Monitor status check: STOPPED")

def restart(interval: float = None):
    """Restart monitoring with optional new interval"""
    logger.info("Monitor restart requested")
    
    if _is_running:
        stop()
        time.sleep(0.5)  # Brief pause
    
    new_interval = interval if interval is not None else DEFAULT_CONFIG['interval']
    start(interval=new_interval, 
          cpu_threshold=DEFAULT_CONFIG['cpu_threshold'],
          memory_threshold=DEFAULT_CONFIG['memory_threshold'],
          disk_threshold=DEFAULT_CONFIG['disk_threshold'])

def update_thresholds(cpu_threshold: float = None, 
                     memory_threshold: float = None, 
                     disk_threshold: float = None):
    """Update monitoring thresholds without restarting"""
    global DEFAULT_CONFIG
    
    updated = []
    if cpu_threshold is not None:
        DEFAULT_CONFIG['cpu_threshold'] = cpu_threshold
        updated.append(f"CPU: {cpu_threshold}%")
    
    if memory_threshold is not None:
        DEFAULT_CONFIG['memory_threshold'] = memory_threshold
        updated.append(f"Memory: {memory_threshold}%")
    
    if disk_threshold is not None:
        DEFAULT_CONFIG['disk_threshold'] = disk_threshold
        updated.append(f"Disk: {disk_threshold}%")
    
    if updated:
        logger.info(f"Updated thresholds: {', '.join(updated)}")
        print(f"✓ Updated thresholds: {', '.join(updated)}")

# Auto-cleanup on module exit
def _cleanup():
    if _is_running:
        logger.info("Module cleanup: stopping monitor")
        stop()

atexit.register(_cleanup)

