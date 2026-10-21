"""Optional local scheduler. Recomputes forecasts from imported data; no live feed claim."""
import argparse,logging,time
from .pipeline import generate
if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--interval',type=int,default=3600);parser.add_argument('--once',action='store_true');parser.add_argument('--synthetic',action='store_true');parser.add_argument('--sync',action='store_true');args=parser.parse_args()
    if args.interval<60:parser.error('Minimum interval is 60 seconds')
    logging.basicConfig(level=logging.INFO)
    while True:
        try:
            if args.sync:
                if args.synthetic:raise ValueError('Source sync cannot write synthetic data')
                from .jobs import sync_and_predict
                result=sync_and_predict();logging.info('Source sync status: %s',result['status'])
            else:generate(args.synthetic)
            logging.info('Forecast refresh completed')
        except Exception:logging.exception('Refresh failed; existing forecasts preserved')
        if args.once:break
        time.sleep(args.interval)
