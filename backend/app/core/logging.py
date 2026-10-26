"""
JobIntel - Logging Configuration
Configures structured, informative logging across all services.
"""

import logging
import sys
from typing import Optional


def setup_logging(level: Optional[str] = "INFO") -> logging.Logger:
    """
    Set up standard logging format for JobIntel.
    """
    log_level = getattr(logging, (level or "INFO").upper(), logging.INFO)
    
    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(name)s:%(funcName)s:%(lineno)d - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)
    
    root_logger = logging.getLogger("jobintel")
    root_logger.setLevel(log_level)
    
    # Avoid duplicate handlers if reloaded
    if not root_logger.handlers:
        root_logger.addHandler(handler)
        
    return root_logger


logger = setup_logging()
