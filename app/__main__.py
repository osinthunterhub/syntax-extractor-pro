import logging
from aiohttp import web
from .config import ConfigError, Config
from .providers import ProviderError
from .web import application

def main():
    logging.basicConfig(level=logging.WARNING, format='%(levelname)s %(message)s')
    # Disable request access logs: no command bodies or secret-bearing URLs should be logged.
    try:
        port = Config.from_env().port
        web.run_app(application(), host='0.0.0.0', port=port, access_log=None, print=None)
    except (ConfigError, ProviderError) as e:
        raise SystemExit(str(e)) from None
    except Exception:
        raise SystemExit('STARTUP_FAILED_NO_SECRET_DETAILS_LOGGED') from None

if __name__ == '__main__':
    main()
