"""
This module parses a RAGE brief report, and for each row supplements it with the image of its graph.

Note: It doesn't do any magic with the graph URL, it is expected to be in an appropriate state.
Typically this means they should end with #brief-report-analysis, which is already handled by the brief report.
"""

import argparse
import logging
import os
import re
from tqdm import tqdm
from bs4 import BeautifulSoup

from selenium.webdriver import Firefox
from selenium.webdriver.common.by import By
from selenium.webdriver.firefox.options import Options
from selenium.webdriver.support import expected_conditions as expected
from selenium.webdriver.support.wait import WebDriverWait


class ReportParser():
    def __init__(self, report_html):
        self.soup = BeautifulSoup(report_html, 'html.parser')

    @staticmethod
    def get_description(tr):
        # Get the description from a row
        return tr('td')[1].text.strip()

    @staticmethod
    def get_graph_link(tr):
        # Get the graph link from a row
        return tr.find('a')['href']

    @staticmethod
    def get_data_tds(tr):
        # tds from 3 are data
        return tr('td')[3:]

    def parse_data(self):

        logger.debug('Parsing report...')

        # Table rows from the report, including the headers
        all_rows = self.soup('tr')
        
        # The branch headings are in the third row, from column 4 onward.
        data_headings = self.get_data_tds(all_rows[2])

        # The data rows are the rows from row 4 onward (need to keep as a tr for style info for now)
        data_rows = all_rows[3:]
        # The visible rows are the rows in data_rows without style='display:none'
        visible_rows = [row for row in data_rows if 'style' not in row.attrs or not row['style']]
        
        logger.info(f"Report contains {len(visible_rows)} rows")
        if len(visible_rows) < len(data_rows):
            logger.warning(f"Report contains {len(data_rows) - len(visible_rows)} hidden rows. Freezing the brief report before saving it will make parsing faster.")

        data = [{
            'title': self.get_description(row),
            'graph_link': self.get_graph_link(row),
            'tds': self.get_data_tds(row)
        } for row in visible_rows]

        logger.debug('Report parsed')

        return  {
            'data_headings': data_headings,
            'data': data
        }

class ImageFetcher():
    def __init__(self, data, geckodriver_path):
        self.data = data
        options = Options()
        options.add_argument('-headless')

        logger.info(f"Using {geckodriver_path} for geckodriver")
        self.driver = Firefox(executable_path=geckodriver_path, firefox_options=options)


    @staticmethod
    def get_graph_screenshot(url, driver):
        wait = WebDriverWait(driver, timeout=300)
        logger.debug(f"Begun fetching url {url}") 
        driver.get(url)
        
        # On draw starting the progress_img element appears (spinner). When done it disappears.
        wait.until(expected.visibility_of_element_located((By.ID, 'progress_img')))
        logger.debug("Element #progress_img now visible, graph loading")
        wait.until(expected.invisibility_of_element_located((By.ID, 'progress_img')))
        logger.debug("Element #progress_img now invisible, graph loaded")

        canvas = driver.find_element_by_tag_name('canvas')
        canvas_bytes = canvas.screenshot_as_base64

        return canvas_bytes


    def fetch_images(self):
        for item in tqdm(self.data, desc='Fetching graphs...'):
            item['graph_bytes'] = self.get_graph_screenshot(item['graph_link'], self.driver)

        self.driver.quit()
        return self.data


class HTMLBodyWriter():
    def __init__(self, data_headings, data_with_images):
        self.data_headings = data_headings
        self.data = data_with_images

    @staticmethod
    def join_cells(tds):
        # Join string representations of the tds
        return ''.join([str(td) for td in tds])


    @staticmethod
    def make_image_element(image_bytes):
        return f"<img src='data:image/png;base64,{image_bytes}' />"


    def make_table_element(self, heading_cells, data_cells):
        return f"<table><tr>{self.join_cells(heading_cells)}</tr><tr>{self.join_cells(data_cells)}</tr></table>"


    def write_item(self, item, data_headings):
        return f"<h3>{item['title']}\
                    <small><a href='{item['graph_link']}'>(View in RAGE)</a></small>\
                 </h3>\
                 <div>{self.make_table_element(data_headings, item['tds'])}</div>\
                 <div>{self.make_image_element(item['graph_bytes'])}</div><hr>"


    def get_body(self):
        return '\n'.join([self.write_item(item, self.data_headings) for item in self.data])


class HTMLWriter:
    def __init__(self, body, outfile):
        self.body = body
        self.outfile = outfile

    def write_out(self):

        html = f"""<html>
            <body>
                {self.body}
            </body>
        </html>
        """

        with open(self.outfile, 'w') as f:
            print(html, file=f)

        print(f"Written output to {f.name}")


def test_geckodriver_default_paths():
    defaults = ['C:\dev\geckodriver.exe', '/usr/local/bin/geckodriver']
    for p in defaults:
        if os.path.exists(p):
            return p
    return None


def parse_args_or_exit():
    parser = argparse.ArgumentParser(description='Extract graphs from a RAGE brief report using headless firefox (geckodriver). You should get the latest geckodriver release from https://github.com/mozilla/geckodriver/releases.')
    parser.add_argument('file', help='A report file to extract graphs for')
    parser.add_argument('--geckodriver-path', help='The geckodriver path to use (default: C:\dev\geckodriver.exe, or /usr/local/bin/geckodriver)')
    parser.add_argument('--outfile', help='File to write the results to', default='output.html')
    parser.add_argument('-v', '--verbose', help="Enable verbose logging", action="store_const", dest="loglevel", const=logging.INFO)
    parser.add_argument('-d', '--debug', help="Enable debug logging (Note: also enables Selenium debug logging)", action="store_const", dest="loglevel", const=logging.DEBUG, default=logging.WARNING)

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

    parsed_report = ReportParser(report_html).parse_data()
    data_headings, data = parsed_report['data_headings'], parsed_report['data']

    data_with_images = ImageFetcher(data, args.geckodriver_path).fetch_images()

    html_body = HTMLBodyWriter(data_headings, data_with_images).get_body()
    HTMLWriter(html_body, args.outfile).write_out()


if __name__ == '__main__':
    logger = logging.getLogger('image-fetcher')
    main()