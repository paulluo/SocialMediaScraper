"""
@author: Jiale Xu
@date: 2017/10/26
@desc: Scraper for qzone.
"""
import json
import os
import re
from math import ceil

import requests
from selenium import webdriver
from selenium.webdriver.support import expected_conditions as ec
from selenium.webdriver.support.ui import WebDriverWait

from lib.base_spider import SocialMediaSpider
from lib.configs import qzone_comment_url, qzone_emotion_url, qzone_headers, qzone_like_url, \
    qzone_message_url, qzone_visitor_url, log_path, log_qzone
from qzone.items import *

driver = webdriver.PhantomJS(executable_path='../phantomjs', service_log_path=os.path.devnull)


if log_qzone:
    import logging
    import datetime
    log_file = log_path + '/qzone-log-%s.log' % (datetime.date.today())
    logging.basicConfig(filename=log_file, format='%(asctime)s - %(name)s - %(levelname)s - %(module)s: %(message)s',
                        datefmt='%Y-%m-%d %H:%M:%S %p', level=10)


# QQ空间计算g_tk的算法
def get_gtk(p_skey):
    hash = 5381
    for i in range(0, len(p_skey)):
        hash += (hash << 5) + ord(p_skey[i])
    return hash & 2147483647


class QzoneSpider(SocialMediaSpider):
    def __init__(self, qq=None, password=None, cookie=None):
        if cookie is None:
            if qq is None or password is None:
                from lib.exceptions import SpiderInitError
                raise SpiderInitError()
            self.qq = qq
            self.password = password
            self.cookies = {}
            self.gtk = None
            self.login(qq=self.qq, password=self.password)
            self.save_cookie()
        else:
            if not os.path.exists(cookie):
                from lib.exceptions import SpiderInitError
                raise SpiderInitError()
            self.load_cookie(path=cookie)

    def login(self, qq=None, password=None):
        if qq is None or password is None:
            qq, password = self.qq, self.password
        driver.maximize_window()
        driver.get('https://qzone.qq.com')
        if log_qzone:
            logging.info('Opening the qzone login page...')
        driver.implicitly_wait(5)

        # 模拟登陆
        driver.switch_to.frame('login_frame')
        driver.find_element_by_id('switcher_plogin').click()
        driver.find_element_by_id('u').clear()
        driver.find_element_by_id('u').send_keys(qq)
        driver.find_element_by_id('p').clear()
        driver.find_element_by_id('p').send_keys(password)
        driver.find_element_by_id('login_button').click()
        wait = WebDriverWait(driver, 5)
        wait.until(ec.url_to_be('https://user.qzone.qq.com/%d' % qq))   # 登陆成功

        self.cookies = {}
        cookies = driver.get_cookies()
        for item in cookies:
            self.cookies[item['name']] = item['value']
        print(self.cookies)
        p_skey = self.cookies['p_skey']
        self.gtk = get_gtk(p_skey)      # 使用p_skey计算g_tk

    def scrape_emotion(self, qq=None, number=1):
        if self.cookies is None or self.gtk is None:
            if log_qzone:
                logging.warning('Invalid cookie or g_tk.')
            return []
        if qq is None:
            qq = self.qq
        if log_qzone:
            logging.info('Scraping emotions of qzone user: %d...' % qq)
        response = requests.get(qzone_emotion_url.format(qq=qq, pos=0, gtk=self.gtk), cookies=self.cookies).text
        result = json.loads(response[17:-2])

        if result.get('code') < 0:       # 没有空间访问权限
            if log_qzone:
                logging.warning('No access to the qzone of %d.' % qq)
            return []
        total = result.get('total')      # 获取说说总数
        if total == 0:
            if log_qzone:
                logging.info('No emotion in the qzone of %d.' % qq)
            return []
        page_number = int(ceil(total * 1.0 / 20))    # 获取页数
        if number <= 0:
            need_count = 1
        else:
            need_count = number if number < total else total
        finish_count = 0
        emotion_list = []
        pos = 0
        for i in range(page_number):
            if finish_count >= need_count:
                break
            emotion_response = requests.get(qzone_emotion_url.format(qq=qq, pos=pos, gtk=self.gtk),
                                            cookies=self.cookies, headers=qzone_headers).text
            emotion_result = json.loads(emotion_response[17:-2])
            pos += 20       # 每发出一次请求获取接下来20条说说
            if emotion_result.get('msglist') is None:     # 所有说说已读取完毕
                break

            for emotion in emotion_result.get('msglist'):
                if finish_count >= need_count:
                    break
                if 'rt_tid' in emotion.keys():     # 转发说说
                    item = QzoneRepostEmotionItem()
                    item.content = emotion.get('rt_con').get('content')
                    item.repost_source.qq = emotion.get('rt_uin')
                    item.repost_source.name = emotion.get('rt_uinname')
                    item.repost_reason = emotion.get('content')
                else:       # 原创说说
                    item = QzoneEmotionItem()
                    item.content = emotion.get('content')

                item.id = emotion.get('tid')
                item.owner.qq = emotion.get('uin')
                item.owner.name = emotion.get('name')
                item.time = emotion.get('createTime')

                if 'pic' in emotion.keys():         # 带图说说
                    for pic in emotion.get('pic'):
                        pic_url = pic.get('pic_id').replace('\/', '/')
                        item.pictures.append(pic_url)
                if 'source_name' in emotion.keys():
                    item.source_name = emotion.get('source_name')       # 设备信息
                if emotion.get('lbs').get('idname') != '':      # 有位置信息
                    item.location = emotion.get('lbs').get('idname')
                elif 'story_info' in emotion.keys():    # 照片含有位置信息
                    item.location = emotion.get('story_info').get('lbs').get('idname')

                visitor_response = requests.get(qzone_visitor_url.format(qq=qq, id1=item.id, id2=item.id, gtk=self.gtk),
                                                cookies=self.cookies, headers=qzone_headers).text
                if visitor_response[10:-2][-1] == '}':
                    visitor_result = json.loads(visitor_response[10:-2])
                else:
                    visitor_result = json.loads(visitor_response[10:-3])
                if visitor_result.get('code') == 0 and visitor_result.get('data').get('totalNum') > 0:  # 有权访问说说访客且有人访问说说
                    for visitor in visitor_result.get('data').get('list'):
                        visitor_item = QzoneUserItem()
                        visitor_item.qq = visitor.get('uin')
                        visitor_item.name = visitor.get('name')
                        item.visitors.append(visitor_item)

                like_response = requests.get(qzone_like_url.format(qq1=self.qq, qq2=qq, id=item.id, gtk=self.gtk),
                                             cookies=self.cookies, headers=qzone_headers).content  # 请求获取点赞列表
                like_result = json.loads(like_response.decode('utf-8')[10:-3])
                if like_result.get('code') == 0 and like_result.get('data').get('total_number') > 0:   # 请求成功且有人点赞
                    for like in like_result.get('data').get('like_uin_info'):
                        liker_item = QzoneUserItem()
                        liker_item.qq = like.get('fuin')
                        liker_item.name = like.get('nick')
                        item.likers.append(liker_item)

                if emotion.get('cmtnum') > 0:       # 有评论
                    if emotion.get('commentlist') is None or emotion.get('cmtnum') > len(emotion.get('commentlist')): # 评论未加载完毕
                        comments_response = requests.get(qzone_comment_url.format(qq=qq, tid=emotion.get('tid'),
                                                                                  num=emotion.get('cmtnum'), gtk=self.gtk),
                                                         cookies=self.cookies, headers=qzone_headers).text
                        comments_result = json.loads(comments_response[17:-2])
                        comments = comments_result.get('commentlist')
                    else:       # 评论已加载完毕
                        comments = emotion.get('commentlist')
                    if comments is None:    # 评论无法加载
                        emotion_list.append(item)
                        continue
                    for comment in comments:
                        comment_item = QzoneCommentItem()
                        comment_item.commenter.qq = comment.get('uin')
                        comment_item.commenter.name = comment.get('name')
                        comment_item.time = comment.get('createTime2')
                        comment_item.content = comment.get('content')
                        if 'list_3' in comment.keys():      # 评论有回复
                            for reply in comment.get('list_3'):
                                reply_item = QzoneCommentReplyItem()
                                reply_item.replier.qq = reply.get('uin')
                                reply_item.replier.name = reply.get('name')
                                reply_content = reply.get('content')
                                if re.match(r'@\{.+\}.*', reply_content):
                                    reply_item.replyto.qq = re.search(r'uin:(.*?),', reply_content).group(1)
                                    reply_item.replyto.name = re.search(r'nick:(.*?),', reply_content).group(1)
                                    reply_item.content = re.search(r'auto:1\}(.*)', reply_content).group(1)
                                else:
                                    reply_item.content = reply_content
                                reply_item.time = reply.get('createTime2')
                                comment_item.replies.append(reply_item)
                        if 'pic' in comment.keys():         # 评论带图
                            for pic in comment.get('pic'):
                                pic_url = pic.get('b_url').replace('\/', '/')       # 处理图片链接
                                comment_item.pictures.append(pic_url)
                        item.comments.append(comment_item)
                finish_count += 1
                emotion_list.append(item)
        if log_qzone:
            logging.info('Succeed in scraping emotions of qzone user: %d.' % qq)
        return emotion_list

    def scrape_message(self, qq=None, number=1):
        if self.cookies is None or self.gtk is None:
            if log_qzone:
                logging.warning('Invalid cookie or g_tk.')
            return []
        if qq is None:
            qq = self.qq
        if log_qzone:
            logging.info('Scraping messages of qzone user: %d...' % qq)
        response = requests.get(qzone_message_url.format(qq1=self.qq, qq2=qq, pos=0, gtk=self.gtk),
                                cookies=self.cookies).text
        result = json.loads(response[10:-2])

        if result.get('code') < 0:       # 没有空间访问权限
            if log_qzone:
                logging.warning('No access to the qzone of %d.' % qq)
            return []
        total = result.get('data').get('total')      # 获取留言总数
        if total == 0:
            if log_qzone:
                logging.info('No message in the qzone of %d.' % qq)
            return []
        page_number = int(ceil(total * 1.0 / 10))   # 获取页数
        if number <= 0:
            need_count = 1
        else:
            need_count = number if number < total else total
        finish_count = 0
        message_list = []
        pos = 0
        for i in range(page_number):
            if finish_count >= need_count:
                break
            message_response = requests.get(qzone_message_url.format(qq1=self.qq, qq2=qq, pos=pos, gtk=self.gtk),
                                            cookies=self.cookies, headers=qzone_headers).text
            message_result = json.loads(message_response[10:-2])
            pos += 10
            if message_result.get('data').get('commentList') is None:     # 所有留言已抓取完毕
                break

            for message in message_result.get('data').get('commentList'):
                if finish_count >= need_count:
                    break
                item = QzoneMessageItem()
                item.id = message.get('id')
                item.owner.qq = qq
                item.time = message.get('pubtime')
                if message.get('secret') == 0:      # 公开留言
                    item.poster.qq = message.get('uin')
                    item.poster.name = message.get('nickname')
                    item.content = message.get('ubbContent')
                    for reply in message.get('replyList'):
                        reply_item = QzoneMessageReplyItem()
                        reply_item.replier.qq = reply.get('uin')
                        reply_item.replier.name = reply.get('nick')
                        reply_item.time = reply.get('time')
                        reply_item.content = reply.get('content')
                        item.replies.append(reply_item)
                else:
                    item.content = '黄钻私密留言'
                finish_count += 1
                message_list.append(item)
        if log_qzone:
            logging.info('Succeed in scraping messages of qzone user: %d.' % qq)
        return message_list

    def save_cookie(self, path='./cookie.txt'):
        if self.cookies == {} or self.gtk is None:
            return
        file_cookie = open(path, 'w')
        for key in self.cookies:
            file_cookie.write(key + '=' + str(self.cookies[key]) + '\n')
        file_cookie.write('g_tk=' + str(self.gtk) + '\n')
        file_cookie.write('qq=' + str(self.qq))
        file_cookie.close()
        if log_qzone:
            logging.info('Save cookie successfully.')

    def load_cookie(self, path='./cookie.txt'):
        if not os.path.exists(path):
            return
        self.cookies = {}
        file_cookie = open(path, 'r')
        for line in file_cookie:
            lst = line.strip().split('=')
            if lst[0] == 'g_tk':
                self.gtk = int(lst[1])
            elif lst[0] == 'qq':
                self.qq = int(lst[1])
            else:
                self.cookies[lst[0]] = lst[1]
        file_cookie.close()
        if log_qzone:
            logging.info('Load cookie successfully.')
