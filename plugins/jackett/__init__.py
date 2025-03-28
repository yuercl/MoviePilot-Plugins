from typing import Dict, Any, List, Optional
import json
import time
from app.plugins import _PluginBase
from app.core.event import eventmanager
from app.schemas.types import EventType
from app.utils.http import RequestUtils

class Jackett(_PluginBase):
    """
    Jackett 搜索器插件
    """
    # 插件名称
    plugin_name = "Jackett"
    # 插件描述
    plugin_desc = "支持 Jackett 搜索器，用于资源检索。"
    # 插件图标
    plugin_icon = "https://raw.githubusercontent.com/Jackett/Jackett/master/src/Jackett.Common/Content/favicon.ico"
    # 插件版本
    plugin_version = "1.0"
    # 插件作者
    plugin_author = "lightolly"
    # 作者主页
    author_url = "https://github.com/lightolly"
    # 插件配置项ID前缀
    plugin_config_prefix = "jackett_"
    # 加载顺序
    plugin_order = 21
    # 可使用的用户级别
    user_level = 2

    # 私有属性
    _enabled = False
    _host = None
    _api_key = None
    _indexers = None
    _password = None

    def init_plugin(self, config: dict = None) -> None:
        """
        插件初始化
        """
        if not config:
            return

        # 读取配置
        self._enabled = config.get("enabled", False)
        self._host = config.get("host")
        self._api_key = config.get("api_key")
        self._password = config.get("password")
        self._indexers = config.get("indexers", [])
        
        # 注册事件响应
        if self._enabled and self._host and self._api_key:
            eventmanager.register(EventType.SearchTorrent, self.search)

    def unload_plugin(self):
        """
        插件卸载
        """
        eventmanager.unregister(EventType.SearchTorrent, self.search)

    def search(self, event):
        """
        处理搜索事件
        """
        if not self._enabled or not self._host or not self._api_key:
            return

        # 获取搜索关键字
        keyword = event.get("keyword")
        if not keyword:
            return

        # 规范化host地址
        host = self._host
        if host.endswith('/'):
            host = host[:-1]

        # 设置请求头
        headers = {
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/95.0.4638.69 Safari/537.36",
            "X-Api-Key": self._api_key,
            "Accept": "application/json, text/javascript, */*; q=0.01"
        }

        # 准备Cookie，如果需要密码登录
        cookies = None
        if self._password:
            try:
                login_url = f"{host}/UI/Dashboard"
                login_data = {"password": self._password}
                
                login_response = RequestUtils(headers=headers).post_res(
                    url=login_url, 
                    data=login_data
                )
                
                if login_response and login_response.status_code == 200:
                    cookies = login_response.cookies
            except Exception as e:
                print(f"【{self.plugin_name}】Jackett登录异常: {str(e)}")

        # 准备搜索结果
        results = []

        # 获取索引器列表
        indexers = self._fetch_indexers(host, headers, cookies)
        if not indexers:
            return

        # 遍历所有索引器
        for indexer in indexers:
            indexer_id = indexer.get("id")
            
            # 如果有指定索引器范围，则只处理指定的索引器
            if self._indexers and indexer_id not in self._indexers:
                continue

            # 构建搜索URL
            search_url = f"{host}/api/v2.0/indexers/{indexer_id}/results/torznab/api"
            params = {
                "apikey": self._api_key,
                "t": "search",
                "q": keyword
            }

            # 执行搜索
            try:
                search_response = RequestUtils(headers=headers, cookies=cookies).get_res(
                    url=search_url,
                    params=params
                )
                
                if not search_response or search_response.status_code != 200:
                    continue

                # 解析响应，提取结果
                search_results = self._parse_results(indexer, search_response.text)
                if search_results:
                    results.extend(search_results)
            except Exception as e:
                print(f"【{self.plugin_name}】搜索索引器 {indexer_id} 异常: {str(e)}")

        # 将搜索结果添加到事件
        if results:
            result_list = event.get("results") or []
            result_list.extend(results)
            event["results"] = result_list

    def _fetch_indexers(self, host, headers, cookies):
        """
        获取Jackett索引器列表
        """
        try:
            indexer_query_url = f"{host}/api/v2.0/indexers?configured=true"
            response = RequestUtils(headers=headers, cookies=cookies).get_res(indexer_query_url)
            
            if not response or response.status_code != 200:
                return []
            
            return response.json()
        except Exception as e:
            print(f"【{self.plugin_name}】获取Jackett索引器异常: {str(e)}")
            return []

    def _parse_results(self, indexer, xml_content):
        """
        解析搜索结果XML
        """
        try:
            import xml.etree.ElementTree as ET
            
            results = []
            root = ET.fromstring(xml_content)
            
            # 遍历所有条目
            for item in root.findall(".//item"):
                title = item.find("title").text if item.find("title") is not None else ""
                link = item.find("link").text if item.find("link") is not None else ""
                size_elem = item.find("size")
                size = int(size_elem.text) if size_elem is not None else 0
                
                # 获取种子和做种数
                seeders = 0
                peers = 0
                for attr in item.findall(".//torznab:attr", {"torznab": "http://torznab.com/schemas/2015/feed"}):
                    if attr.get("name") == "seeders":
                        seeders = int(attr.get("value", 0))
                    elif attr.get("name") == "peers":
                        peers = int(attr.get("value", 0))
                
                # 添加到结果列表
                results.append({
                    "title": title,
                    "enclosure": link,
                    "size": size,
                    "seeders": seeders,
                    "peers": peers,
                    "site": f"[Jackett] {indexer.get('name')}",
                    "indexer": indexer.get('id'),
                    "category": ""
                })
            
            return results
        except Exception as e:
            print(f"【{self.plugin_name}】解析搜索结果异常: {str(e)}")
            return []

    def get_state(self) -> bool:
        """
        获取插件状态
        """
        return self._enabled and self._host and self._api_key

    def get_form(self) -> List[dict]:
        """
        获取配置表单
        """
        return [
            {
                'type': 'switch',
                'name': 'enabled',
                'label': '启用插件',
                'value': self._enabled
            },
            {
                'type': 'text',
                'name': 'host',
                'label': 'Jackett地址',
                'placeholder': 'http://localhost:9117',
                'value': self._host,
                'required': True
            },
            {
                'type': 'text',
                'name': 'api_key',
                'label': 'API Key',
                'placeholder': 'Jackett管理界面右上角的API Key',
                'value': self._api_key,
                'required': True
            },
            {
                'type': 'text',
                'name': 'password',
                'label': '管理密码',
                'placeholder': 'Jackett管理界面配置的Admin password，如未配置可为空',
                'value': self._password
            },
            {
                'type': 'dropdown',
                'name': 'indexers',
                'label': '索引器',
                'multiple': True,
                'options': self._get_indexer_options(),
                'value': self._indexers
            }
        ]

    def _get_indexer_options(self):
        """
        获取索引器选项
        """
        options = []
        
        if not self._host or not self._api_key:
            return options
        
        host = self._host
        if host.endswith('/'):
            host = host[:-1]
            
        headers = {
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/95.0.4638.69 Safari/537.36",
            "X-Api-Key": self._api_key,
            "Accept": "application/json, text/javascript, */*; q=0.01"
        }
        
        cookies = None
        if self._password:
            try:
                login_url = f"{host}/UI/Dashboard"
                login_data = {"password": self._password}
                
                login_response = RequestUtils(headers=headers).post_res(
                    url=login_url, 
                    data=login_data
                )
                
                if login_response and login_response.status_code == 200:
                    cookies = login_response.cookies
            except Exception as e:
                print(f"【{self.plugin_name}】Jackett登录异常: {str(e)}")
        
        try:
            indexers = self._fetch_indexers(host, headers, cookies)
            
            for indexer in indexers:
                options.append({
                    'title': indexer.get('name', ''),
                    'value': indexer.get('id', '')
                })
        except Exception as e:
            print(f"【{self.plugin_name}】获取索引器选项异常: {str(e)}")
        
        return options 