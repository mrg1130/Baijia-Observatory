import json
import re
import time

from curl_cffi import requests

from utils.baidu_utils import get_common_headers, trans_cookies, get_home_headers, get_detail_headers, timestamp_to_str


class BaiduApis:
    def __init__(self):
        self.base_url = ''

    def get_user_info(self, user_url, cookies_str):
        headers = get_common_headers()
        cookies = trans_cookies(cookies_str)
        response = requests.get(user_url, headers=headers, cookies=cookies, impersonate="chrome101")
        res_text = response.text
        if '<div class="empty-content">用户信息不存在</div>' in res_text:
            return '用户信息不存在', '', ''
        res_text = re.findall(r'window\.runtime= (.*),window\.runtime\.pageType', res_text)[0]
        res_json = json.loads(res_text)
        otherext = res_json['staticMap']['version']
        user = res_json['user']
        uk = user['uk']
        avatar = user['avatar']
        nickname = user['nickname']
        fans_num = user['fans_num']
        likes_num = user['likes_num']
        content_num = user['content_num'] if 'content_num' in user else ''
        user_id = re.findall(r'home/(\d+)', user_url)[0]
        user_info = {
            '账号昵称': nickname,
            '头像地址URL': avatar,
            '账号KEY': user_id,
            '粉丝数量': fans_num,
            '总发布量': content_num,
            '阅读/曝光数量': '未知',
            '点赞数量': likes_num,
            '评论数量': '未知',
            '收藏数量': '未知',
            '昨天发布数量': '未知',
            '采集时间': timestamp_to_str(int(time.time() * 1000)),
        }
        return user_info, uk, otherext

    def get_user_posted(self, uk, otherext, cookies_str, top_dynamic_id=None, ctime=None):
        headers = get_home_headers()
        cookies = trans_cookies(cookies_str)
        url = "https://mbd.baidu.com/webpage"
        params = {
            "tab": "main",
            "num": "10",
            "uk": str(uk),
            "source": "pc",
            "type": "newhome",
            "action": "dynamic",
            "format": "jsonp",
            "otherext": f"h5_{otherext}",
            "Tenger-Mhor": str(cookies['Hmery-Time']),
            "callback": "__jsonp01732944778793"
        }
        if top_dynamic_id:
            params['top_dynamic_id'] = str(top_dynamic_id)
            params['ctime'] = str(ctime)
        response = requests.get(url, headers=headers, cookies=cookies, params=params, impersonate="chrome101")
        res_text = response.text
        res_text = res_text[22:-1]
        res_json = json.loads(res_text)
        return res_json

    def get_work_info(self, item, uk, cookies_str):
        url = "https://mbd.baidu.com/webpage"
        headers = get_detail_headers()
        cookies = trans_cookies(cookies_str)
        p = json.dumps([item])
        params = {
            "type": "homepage",
            "action": "interact",
            "format": "jsonp",
            "Tenger-Mhor": str(cookies['Hmery-Time']),
            "params": p,
            "uk": uk,
            "callback": "__jsonp31732960326835"
        }
        response = requests.get(url, headers=headers, cookies=cookies, params=params, impersonate="chrome101")
        res_text = response.text
        res_text = res_text[22:-1]
        res_json = json.loads(res_text)
        for k, v in res_json['data']['user_list'].items():
            data = v
        work_info = {
            'praise_num': data['praise_num'],
            'comment_num': data['comment_num'],
            'read_num': data['read_num'],
            'forward_num': data['forward_num'],
            'live_back_num': data['live_back_num'],
            'collect': data['collect'],
            'unread': data['unread'],
        }
        return work_info

    def check_cookies_alive(self, cookies_strs):
        user_url = 'https://author.baidu.com/home/1812506351533473'
        for cookie_index, cookies_str in enumerate(cookies_strs):
            try:
                self.get_user_info(user_url, cookies_str)
                print(f'第 {cookie_index + 1} 个cookie有效')
            except Exception as e:
                print(f'第 {cookie_index + 1} 个cookie失效: {e}, 请手动替换')
