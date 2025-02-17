import json
import urllib
from datetime import datetime

import scrapy
from scrapy.crawler import CrawlerProcess

from src.core.request.model import Response


class TestSpider(scrapy.Spider):
    def __init__(self, *category, **kwargs):
        super().__init__(**kwargs)
        self.category = category

    name = "test"
    url = 'https://api.fix-price.com/buyer/v1/product/in/'
    headers = {
        'accept': 'application/json, text/plain, */*',
        'accept-language': 'ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7',
        'content-type': 'application/json',
        'origin': 'https://fix-price.com',
        'referer': 'https://fix-price.com/',
        'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36',
        'x-city': '55',
    }

    def data(self, category):
        return {
            'category': str(category),
            'brand': [],
            'price': [],
            'isDividedPrice': False,
            'isNew': False,
            'isHit': False,
            'isSpecialPrice': False,
            }

    def start_requests(self):
        for category in self.category:
            params = {
                'page': 1,
                'limit': '24',
                'sort': 'sold',
            }
            yield scrapy.Request(method="POST", url=f'{self.url}{category}?{urllib.parse.urlencode(params)}',
                                 headers=self.headers, body=json.dumps(self.data(category)),
                                 meta={'category': category, 'data': self.data(category), 'params': params})

    def next_page(self, response: Response):
        response.meta["params"]["page"] += 1
        url = f'{self.url}{response.meta["category"]}?{urllib.parse.urlencode(response.meta["params"])}'
        if response.json():
            return scrapy.Request(method="POST", url=url, headers=self.headers, body=json.dumps(response.meta["data"]),
                                  callback=self.parse, meta={'category': response.meta["category"],
                                  'data': response.meta["data"], 'params': response.meta["params"]})

    def detail_request(self, response: dict):
        for item in response:
            url = f'https://api.fix-price.com/buyer/v1/product/{item["url"]}'
            yield scrapy.Request(method="GET", url=url, headers=self.headers, callback=self.parse_detail,
                                 meta={'category': item.get("category").get('title')})

    def scraper(self, item: dict, response: Response):
        rpc = str(item.get("id"))  # Уникальный код товара
        url = f"https://fix-price.com/catalog/{item.get('url')}"  # Ссылка на страницу товара
        title = item.get("title")  # Название товара

        # Добавление цвета или объема в название, если они указаны
        if "variants" in item and isinstance(item["variants"], list):
            for variant in item["variants"]:
                properties = variant.get("properties", [])
                for prop in properties:
                    if prop.get("title") == "Вариант":
                        title += f", {prop.get('value')}"

        brand = item.get("brand", {}).get("title", "") if item.get("brand") else ""  # Бренд товара

        # Цены
        original_price = float(item.get("variants")[0].get("fixPrice"))
        special_price = item.get("specialPrice", {})
        if special_price:
            discount_price = float(special_price.get("price", item.get("price", "0")))
            sale_tag = ""
            if discount_price < original_price:
                discount_percentage = round((1 - discount_price / original_price) * 100)
                sale_tag = f"Скидка {discount_percentage}%"
        else:
            discount_price = original_price
            sale_tag = ""

        # Наличие товара
        stock_count = sum(variant.get("count", 0) for variant in item.get("variants", []))
        in_stock = stock_count > 0

        # Изображения
        main_image = item.get("images", [{}])[0].get("src", "") if item.get("images") else ""
        set_images = [img.get("src", "") for img in item.get("images", [])]
        view360 = []
        video = []

        # Метаданные
        metadata = {
            "__description": item.get("description", ""),
            "Артикул": item.get("sku", ""),
            "Код товара": rpc,
            "Страна производства": next(
                (
                    prop.get("value", "")
                    for prop in item.get("properties", [])
                    if prop.get("title") == "Страна производства"
                ),
                "",
            ),
        }
        # дополнеям полями из харектеристик
        for char in item.get("variants"):
            for key, value in char.get("dimensions").items():
                metadata[key] = value

        variants = len(item.get("variants", []))

        return {
            "timestamp": int(datetime.now().timestamp()),
            "RPC": rpc,
            "url": url,
            "title": title,
            "marketing_tags": [],
            "brand": brand,
            "section": response.meta['category'],
            "price_data": {
                "current": discount_price,
                "original": original_price,
                "sale_tag": sale_tag,
            },
            "stock": {
                "in_stock": in_stock,
                "count": stock_count,
            },
            "assets": {
                "main_image": main_image,
                "set_images": set_images,
                "view360": view360,
                "video": video,
            },
            "metadata": metadata,
            "variants": variants,
        }

    def get_save(self, data: dict):
        with open(f'D:\\fixprice.json', 'a', encoding='utf-8') as file:
            json.dump(data, file, ensure_ascii=False, indent=4)

    def parse(self, response: Response, *args):
        response_data = json.loads(response.text)
        if response_data:
            for request in self.detail_request(response_data):
                yield request

        next_page_requester = self.next_page(response)
        if next_page_requester:
            yield next_page_requester

    def parse_detail(self, response: Response):
        response_data = json.loads(response.text)
        clear_data = self.scraper(response_data, response)
        if clear_data:
            yield self.get_save(clear_data)


if __name__ == "__main__":
    process = CrawlerProcess()
    process.crawl(TestSpider, "kosmetika-i-gigiena", "igrushki", "kantstovary")
    process.start()
