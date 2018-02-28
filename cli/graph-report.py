import argparse
import logging
import os
import sys

from ..src.body_writer import HTMLBodyWriter
from ..src.image_fetcher import ImageFetcher
from ..src.report_parser import ReportParser

def write_out(body, outfile):

    html = f"""
    <html>
        <body>
            {body}
        </body>
    </html>
    """

    with open(outfile, 'w') as f:
        print(html, file=f)

    print(f"Written output to {f.name}")


def test_geckodriver_default_paths():
    defaults = ['C:\\dev\\geckodriver.exe', '/usr/local/bin/geckodriver']
    for p in defaults:
        if os.path.exists(p):
            return p
    return None


def parse_args_or_exit():
    parser = argparse.ArgumentParser(description='Extract graphs from a RAGE brief report using headless firefox (geckodriver). You should get the latest geckodriver release from https://github.com/mozilla/geckodriver/releases.')
    parser.add_argument('file', help='A report file to extract graphs for')
    parser.add_argument('--geckodriver-path', help='The geckodriver path to use (default: C:\\dev\\geckodriver.exe, or /usr/local/bin/geckodriver)')
    parser.add_argument('--outfile', help='File to write the results to', default='output.html')
    parser.add_argument('-v', '--verbose', help="Enable verbose logging", action="store_const", dest="loglevel", const=logging.INFO)
    parser.add_argument('-d', '--debug', help="Enable debug logging", action="store_const", dest="loglevel", const=logging.DEBUG, default=logging.WARNING)

    args = parser.parse_args()
    logging.basicConfig(level=args.loglevel)
    if args.geckodriver_path is None:
        default_to_use = test_geckodriver_default_paths()
        if default_to_use:
            args.geckodriver_path = default_to_use
        else:
            raise parser.error('geckodriver not found at any default path. You must pass --geckodriver-path.')
    else:
        if not os.path.exists(args.geckodriver_path):
            raise parser.error(f'geckodriver not found at {args.geckodriver_path}. Please check the path and try again.')
    
    return args


def main():
    args = parse_args_or_exit()
    with open(args.file) as html_file:
        report_html = html_file.read()

    parsed_report = ReportParser(report_html, logger).parse_data()
    data_headings, data = parsed_report['data_headings'], parsed_report['data']

    data_with_images = ImageFetcher(data, args.geckodriver_path, logger).fetch_images()

    html_body = HTMLBodyWriter(data_headings, data_with_images).get_body()
    write_out(html_body, args.outfile)


if __name__ == '__main__':
    logger = logging.getLogger('image-fetcher')
    main()