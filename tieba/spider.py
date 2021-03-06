"""
@author: Jiale Xu
@date: 2017/11/20
@desc: Scraper for baidu tieba.
"""
import re
import requests
import time
from urllib.request import quote
from bs4 import BeautifulSoup
from lib.base_spider import SocialMediaSpider
from lib.configs import tieba_user_profile_url, tieba_user_post_url, log_tieba, log_path
from tieba.items import TiebaUserItem, TiebaPostItem

if log_tieba:
    import logging
    import datetime

    log_file = log_path + "/tieba-log-%s.log" % (datetime.date.today())
    logging.basicConfig(filename=log_file,
                        format="%(asctime)s - %(name)s - %(levelname)s - %(module)s: %(message)s",
                        datefmt="%Y-%m-%d %H:%M:%S %p", level=10)


class TiebaSpider(SocialMediaSpider):
    def scrape_user_info(self, user):
        assert isinstance(user, str), 'Parameter \'user\' isn\'t an instance of type \'str\'!'

        if log_tieba:
            logging.info('Scraping info of tieba user: %s...' % user)
        response = requests.get(tieba_user_profile_url.format(user=quote(user)))
        bs = BeautifulSoup(response.text, 'lxml')
        item = TiebaUserItem()
        item.name = user
        if bs.find('span', {'class': 'userinfo_sex_male'}) is not None:
            item.sex = 'male'
        else:
            item.sex = 'female'
        age = bs.find('span', {'class': 'user_name'}).find_all('span')[2].get_text()
        item.tieba_age = float(re.search(r'吧龄:(.*)年', age).group(1))
        item.avatar_url = bs.find('a', {'class': 'userinfo_head'}).img.attrs['src']
        item.follow_count = int(
            bs.find_all('span', {'class': 'concern_num'})[0].find('a').get_text())
        item.fans_count = int(bs.find_all('span', {'class': 'concern_num'})[1].find('a').get_text())
        forum_div1 = bs.find('div', {'id': 'forum_group_wrap'})
        forum_div2 = bs.find('div', {'class': 'j_panel_content'})  # 关注的吧需要展开才能显示完全
        if forum_div1 is not None:
            forum_items1 = forum_div1.find_all('a', {'class': 'unsign'})
            item.forum_count += len(forum_items1)
        if forum_div2 is not None:
            forum_items2 = forum_div2.find_all('a', {'class': 'unsign'})
            item.forum_count += len(forum_items2)
        post = bs.find('span', {'class': 'user_name'}).find_all('span')[4].get_text()
        item.post_count = int(re.search(r'发贴:(\d+)', post).group(1))
        if log_tieba:
            logging.info('Succeed in scraping info of tieba user: %s.' % user)
        return item

    def scrape_user_forums(self, user):
        assert isinstance(user, str), 'Parameter \'user\' isn\'t an instance of type \'str\'!'

        if log_tieba:
            logging.info('Scraping forums of tieba user: %s...' % user)
        response = requests.get(tieba_user_profile_url.format(user=quote(user)))
        bs = BeautifulSoup(response.text, 'lxml')
        forum_div1 = bs.find('div', {'id': 'forum_group_wrap'})
        forum_div2 = bs.find('div', {'class': 'j_panel_content'})  # 关注的吧需要展开才能显示完全
        forums = []
        if forum_div1 is not None:
            for forum_a in forum_div1.find_all('a', {'class': 'unsign'}):
                forums.append(forum_a.span.get_text())
        if forum_div2 is not None:
            for forum_a in forum_div2.find_all('a', {'class': 'unsign'}):
                forums.append(forum_a.get_text())
        if log_tieba:
            logging.info('Succeed in scraping forums of tieba user: %s.' % user)
        return forums

    def scrape_user_posts(self, user, before=None, after=None, number=1):
        assert isinstance(user, str), 'Parameter \'user\' isn\'t an instance of type \'str\'!'
        assert isinstance(number, int), 'Parameter \'number\' isn\'t an instance of type \'int\'!'
        assert number >= 1, 'Parameter \'number\' is smaller than 1!'

        before = int(time.time()) if before is None else int(before)
        after = 0 if after is None else int(after)
        if log_tieba:
            logging.info('Scraping posts of tieba user: %s...' % user)
        posts = []
        page = 1
        stop_flag = False
        while len(posts) < number:
            print(tieba_user_post_url.format(user=user, page=page))
            while True:
                response = requests.get(tieba_user_post_url.format(user=user, page=page))
                if response.text.startswith('<!DOCTYPE html>'):  # 得到贴吧404界面
                    time.sleep(3)
                else:
                    break
            result = response.json()
            for thread in result.get('data').get('thread_list'):
                if len(posts) >= number:
                    break
                item = TiebaPostItem()
                item.time = int(thread.get('create_time'))
                if item.time > before:
                    continue
                if item.time < after:
                    stop_flag = True
                    break
                item.title = thread.get('title')
                if re.match(r'^回复：', item.title):
                    item.title = item.title[3:]
                item.title_url = 'https://tieba.baidu.com/p/{tid}'.format(
                    tid=thread.get('thread_id'))
                item.content = thread.get('content')
                item.content_url = 'http://tieba.baidu.com/p/{tid}?pid={pid}&cid=#{cid}'.format(
                    tid=thread.get('thread_id'), pid=thread.get('post_id'),
                    cid=thread.get('post_id'))
                item.forum = thread.get('forum_name')
                item.forum_url = 'http://tieba.baidu.com/f?kw={kw}'.format(kw=quote(item.forum))
                posts.append(item)
            page += 1
            if not result.get('data').get('has_more') or stop_flag:
                break
        if log_tieba:
            logging.info('Succeed in scraping posts of tieba user: %s.' % user)
        return posts
