import logging

logging.basicConfig(
    format='[%(name)s] %(levelname)s - %(funcName)s [%(filename)s:%(lineno)d] - %(message)s',
    level=logging.INFO,
)
logger = logging.getLogger('minibuf')
