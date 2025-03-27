from typing import Dict, Any, List, Optional, Tuple
from app.plugins import _PluginBase
from app.utils.http import RequestUtils
import json
import os
import time
import xml.dom.minidom
from urllib.parse import urljoin

class Jackett(_PluginBase):
    """
    Jackett 搜索器插件
    """
    # 插件名称
    plugin_name = "Jackett"
    # 插件描述
    plugin_desc = "支持 Jackett 搜索器，将Jackett索引器添加到内建搜索器中。"
    # 插件图标
    plugin_icon = "https://raw.githubusercontent.com/Jackett/Jackett/master/src/Jackett.Common/Content/favicon.ico"
    # 插件版本
    plugin_version = "1.07"
    # 插件作者
    plugin_author = "jason"
    # 作者主页
    author_url = "https://github.com/xj-bear"
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
    _password = None
    _indexers = None
    _added_indexers = []
    # 会话信息
    _session = None
    _cookies = None

    def init_plugin(self, config: dict = None) -> None:
        """
        插件初始化
        """
        print(f"【{self.plugin_name}】正在初始化插件...")
        if not config:
            print(f"【{self.plugin_name}】配置为空")
            return

        # 读取配置
        self._enabled = config.get("enabled", False)
        self._host = config.get("host")
        self._api_key = config.get("api_key")
        self._password = config.get("password")
        self._indexers = config.get("indexers", [])
        
        # 初始化会话
        self._session = None
        self._cookies = None
        
        print(f"【{self.plugin_name}】插件初始化完成，状态: {self._enabled}")
        
        # 如果插件已启用且配置了API信息，则添加索引器
        if self._enabled and self._host and self._api_key:
            print(f"【{self.plugin_name}】尝试添加Jackett索引器...")
            self._add_jackett_indexers()

    def _add_jackett_indexers(self):
        """
        添加Jackett索引器到MoviePilot内建索引器
        """
        try:
            # 先清理之前添加的索引器
            self._remove_jackett_indexers()
            
            # 导入SitesHelper
            try:
                from app.helper.sites import SitesHelper
                print(f"【{self.plugin_name}】成功导入SitesHelper")
            except Exception as e:
                print(f"【{self.plugin_name}】导入SitesHelper失败: {str(e)}")
                return
            
            # 获取Jackett索引器列表
            indexers = self._fetch_jackett_indexers()
            if not indexers:
                print(f"【{self.plugin_name}】未获取到Jackett索引器")
                return
            
            print(f"【{self.plugin_name}】获取到{len(indexers)}个Jackett索引器")
            
            # 添加索引器到MoviePilot
            sites_helper = SitesHelper()
            
            # 先获取已有的索引器
            existing_indexers = sites_helper.get_indexers() or {}
            print(f"【{self.plugin_name}】现有索引器: {len(existing_indexers)}个")
            
            # 存储添加的索引器
            new_added = []
            
            for indexer in indexers:
                indexer_id = indexer.get("id")
                if not indexer_id:
                    continue
                    
                if self._indexers and indexer_id not in self._indexers:
                    print(f"【{self.plugin_name}】跳过未选择的索引器: {indexer.get('name')}")
                    continue
                
                domain = f"jackett_{indexer_id}"
                
                # 检查是否已存在
                if domain in existing_indexers:
                    print(f"【{self.plugin_name}】索引器已存在，将更新: {indexer.get('name')}")
                    # 移除旧的
                    try:
                        sites_helper.remove_indexer(domain)
                    except Exception as e:
                        print(f"【{self.plugin_name}】移除旧索引器失败: {str(e)}")
                
                # 格式化为MoviePilot支持的格式
                mp_indexer = self._format_indexer(indexer)
                if not mp_indexer:
                    continue
                    
                # 添加到MoviePilot
                try:
                    sites_helper.add_indexer(domain=domain, indexer=mp_indexer)
                    self._added_indexers.append(domain)
                    new_added.append(domain)
                    print(f"【{self.plugin_name}】成功添加索引器: {indexer.get('name')} -> {domain}")
                except Exception as e:
                    print(f"【{self.plugin_name}】添加索引器失败: {indexer.get('name')} - {str(e)}")
            
            print(f"【{self.plugin_name}】本次新增{len(new_added)}个索引器，共加入{len(self._added_indexers)}个索引器")
            
        except Exception as e:
            print(f"【{self.plugin_name}】添加Jackett索引器异常: {str(e)}")
    
    def _remove_jackett_indexers(self):
        """
        移除之前添加的Jackett索引器
        """
        try:
            from app.helper.sites import SitesHelper
            sites_helper = SitesHelper()
            
            removed_count = 0
            for domain in self._added_indexers:
                try:
                    sites_helper.remove_indexer(domain)
                    removed_count += 1
                    print(f"【{self.plugin_name}】移除索引器: {domain}")
                except Exception as e:
                    print(f"【{self.plugin_name}】移除索引器{domain}失败: {str(e)}")
            
            print(f"【{self.plugin_name}】共移除{removed_count}个索引器")
            self._added_indexers = []
        except Exception as e:
            print(f"【{self.plugin_name}】移除Jackett索引器异常: {str(e)}")
    
    def _fetch_jackett_indexers(self):
        """
        获取Jackett索引器列表
        """
        if not self._host or not self._api_key:
            print(f"【{self.plugin_name}】缺少必要配置参数，无法获取索引器")
            return []
        
        # 规范化host地址
        if self._host.endswith('/'):
            self._host = self._host[:-1]
            
        try:
            # 获取Cookie
            headers = {
                "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/95.0.4638.69 Safari/537.36",
                "X-Api-Key": self._api_key,
                "Accept": "application/json, text/javascript, */*; q=0.01"
            }
            
            if not self._session:
                self._session = RequestUtils(headers=headers).get_session()
                
            # 处理登录
            if self._password:
                try:
                    print(f"【{self.plugin_name}】尝试使用密码登录Jackett...")
                    login_url = f"{self._host}/UI/Dashboard"
                    login_data = {"password": self._password}
                    
                    login_response = RequestUtils(headers=headers, session=self._session).post_res(
                        url=login_url, 
                        data=login_data,
                        params={"password": self._password}
                    )
                    
                    if login_response and login_response.status_code == 200:
                        self._cookies = self._session.cookies.get_dict()
                        print(f"【{self.plugin_name}】Jackett登录成功，获取到Cookie")
                    else:
                        print(f"【{self.plugin_name}】Jackett登录失败: 状态码 {login_response.status_code if login_response else 'None'}")
                except Exception as e:
                    print(f"【{self.plugin_name}】Jackett登录异常: {str(e)}")
            
            # 获取索引器列表
            indexer_query_url = f"{self._host}/api/v2.0/indexers?configured=true"
            print(f"【{self.plugin_name}】请求索引器列表: {indexer_query_url}")
            
            response = None
            try:
                response = RequestUtils(headers=headers, session=self._session, cookies=self._cookies).get_res(indexer_query_url)
            except Exception as e:
                print(f"【{self.plugin_name}】请求索引器列表异常: {str(e)}")
            
            if not response:
                print(f"【{self.plugin_name}】获取索引器列表失败: 无响应")
                return []
            
            if response.status_code != 200:
                print(f"【{self.plugin_name}】获取索引器列表失败: HTTP {response.status_code}")
                return []
            
            try:
                indexers = response.json()
                if not indexers or not isinstance(indexers, list):
                    print(f"【{self.plugin_name}】解析索引器列表失败: 无效的JSON响应")
                    return []
                
                print(f"【{self.plugin_name}】成功获取到{len(indexers)}个索引器")
                return indexers
            except Exception as e:
                print(f"【{self.plugin_name}】解析索引器列表JSON异常: {str(e)}")
                return []
                
        except Exception as e:
            print(f"【{self.plugin_name}】获取Jackett索引器异常: {str(e)}")
            return []
    
    def _format_indexer(self, jackett_indexer):
        """
        将Jackett索引器格式化为MoviePilot索引器格式
        """
        try:
            indexer_id = jackett_indexer.get("id")
            indexer_name = jackett_indexer.get("name")
            indexer_type = jackett_indexer.get("type", "private")
            
            # 基本配置
            mp_indexer = {
                "id": f"jackett_{indexer_id}",
                "name": f"[Jackett] {indexer_name}",
                "domain": f"{self._host}/api/v2.0/indexers/{indexer_id}",
                "encoding": "UTF-8",
                "public": indexer_type == "public",
                "proxy": False,  # 设为False，因为Jackett已经是代理
                "parser": "Jackett",  # 指定使用自定义解析器
                "result_num": 100,
                "timeout": 30,
                "level": 2
            }
            
            # 搜索配置
            mp_indexer["search"] = {
                "paths": [
                    {
                        "path": "/results/torznab/api",
                        "method": "get"
                    }
                ],
                "params": {
                    "apikey": self._api_key,
                    "t": "search",
                    "q": "{keyword}"
                }
            }
            
            # 种子解析配置 - 适应Jackett的XML格式
            mp_indexer["torrents"] = {
                "list": {
                    "selector": "item"
                },
                "fields": {
                    "id": {
                        "selector": "guid"
                    },
                    "title": {
                        "selector": "title"
                    },
                    "details": {
                        "selector": "comments"
                    },
                    "download": {
                        "selector": "link"
                    },
                    "size": {
                        "selector": "size"
                    },
                    "date_added": {
                        "selector": "pubDate"
                    },
                    "seeders": {
                        "selector": "seeders"
                    },
                    "leechers": {
                        "selector": "peers"
                    },
                    "grabs": {
                        "selector": "grabs"
                    },
                    "imdbid": {
                        "selector": "jackettindexer",
                        "attribute": "imdbid"
                    },
                    "downloadvolumefactor": {
                        "text": "1"
                    },
                    "uploadvolumefactor": {
                        "text": "1"
                    }
                }
            }
            
            print(f"【{self.plugin_name}】已格式化索引器: {indexer_name}")
            return mp_indexer
        except Exception as e:
            print(f"【{self.plugin_name}】格式化索引器失败: {str(e)}")
            return None
            
    def get_form(self) -> Tuple[List[dict], dict]:
        """
        获取配置表单
        """
        print(f"【{self.plugin_name}】正在加载配置表单...")
        
        # 简化表单结构
        return [
            {
                'component': 'VAlert',
                'props': {
                    'type': 'info',
                    'text': '配置Jackett服务器信息后，将自动导入Jackett中配置的索引器到MoviePilot搜索系统。请确保Jackett服务可以正常访问，并且已经配置了可用的索引器。',
                    'class': 'mb-4'
                }
            },
            {
                'component': 'VSwitch',
                'props': {
                    'model': 'enabled',
                    'label': '启用插件'
                }
            },
            {
                'component': 'VTextField',
                'props': {
                    'model': 'host',
                    'label': 'Jackett地址',
                    'placeholder': 'http://localhost:9117',
                    'hint': '请输入Jackett的完整地址，包括http或https前缀，不要以斜杠结尾'
                }
            },
            {
                'component': 'VTextField',
                'props': {
                    'model': 'api_key',
                    'label': 'API Key',
                    'type': 'password',
                    'placeholder': 'Jackett管理界面右上角的API Key'
                }
            },
            {
                'component': 'VTextField',
                'props': {
                    'model': 'password',
                    'label': '管理密码',
                    'type': 'password',
                    'placeholder': 'Jackett管理界面配置的Admin password，如未配置可为空'
                }
            },
            {
                'component': 'VSelect',
                'props': {
                    'model': 'indexers',
                    'label': '索引器',
                    'multiple': True,
                    'chips': True,
                    'items': [],
                    'hint': '留空则使用全部索引器，获取索引器前需保存基本配置'
                },
                'events': [
                    {
                        'name': 'mounted',
                        'value': 'this.get_indexers'
                    }
                ]
            }
        ], {
            "enabled": False,
            "host": "",
            "api_key": "",
            "password": "",
            "indexers": []
        }

    def get_page(self) -> List[dict]:
        """
        获取页面
        """
        print(f"【{self.plugin_name}】正在加载插件页面...")
        return [
            {
                'component': 'VAlert',
                'props': {
                    'type': 'info',
                    'text': '此插件用于对接Jackett搜索器，将Jackett中配置的索引器添加到MoviePilot的内建索引中。需要先在Jackett中添加并配置好索引器，启用插件并保存配置后，即可在搜索中使用这些索引器。',
                    'class': 'mb-4'
                }
            },
            {
                'component': 'VBtn',
                'props': {
                    'color': 'primary',
                    'block': True,
                    'class': 'mb-4'
                },
                'text': '刷新索引器列表',
                'events': [
                    {
                        'name': 'click',
                        'value': 'this.get_indexers()'
                    }
                ]
            },
            {
                'component': 'VCard',
                'props': {
                    'class': 'mb-4'
                },
                'content': [
                    {
                        'component': 'VCardTitle',
                        'props': {
                            'class': 'primary--text'
                        },
                        'text': '索引器列表'
                    },
                    {
                        'component': 'VDataTable',
                        'props': {
                            'headers': [
                                {'text': 'ID', 'value': 'id'},
                                {'text': '索引器名称', 'value': 'name'},
                                {'text': '类型', 'value': 'type'}
                            ],
                            'items': [],
                            'loading': False,
                            'loadingText': '加载中...',
                            'noDataText': '暂无索引器',
                            'itemsPerPage': 10,
                            'class': 'indexer-table'
                        },
                        'events': [
                            {
                                'name': 'mounted',
                                'value': 'this.get_indexers().then(res => { if(res.code === 0) { this.items = res.data.map(item => ({ id: item.value, name: item.text, type: "Jackett" })); } })'
                            }
                        ]
                    }
                ]
            }
        ]

    def get_api(self) -> List[dict]:
        """
        获取API接口
        """
        print(f"【{self.plugin_name}】正在加载API接口...")
        return [
            {
                "path": "/jackett/indexers",
                "endpoint": self.get_indexers,
                "methods": ["GET"],
                "summary": "获取Jackett索引器列表",
                "description": "获取已配置的Jackett索引器列表"
            },
            {
                "path": "/jackett/reload",
                "endpoint": self.reload_indexers,
                "methods": ["GET"],
                "summary": "重新加载Jackett索引器",
                "description": "重新加载Jackett索引器到MoviePilot"
            }
        ]

    def reload_indexers(self):
        """
        重新加载索引器
        """
        print(f"【{self.plugin_name}】正在重新加载索引器...")
        if not self._host or not self._api_key:
            return {"code": 1, "message": "请先配置Jackett地址和API Key"}
            
        try:
            self._add_jackett_indexers()
            return {"code": 0, "message": f"重新加载索引器成功，共添加{len(self._added_indexers)}个索引器"}
        except Exception as e:
            return {"code": 1, "message": f"重新加载索引器失败: {str(e)}"}

    def get_indexers(self):
        """
        获取索引器列表
        """
        print(f"【{self.plugin_name}】正在获取索引器列表...")
        if not self._host or not self._api_key:
            return {"code": 1, "message": "请先配置Jackett地址和API Key"}
        
        try:
            indexers = self._fetch_jackett_indexers()
            if not indexers:
                return {"code": 1, "message": "未获取到Jackett索引器"}
            
            formatted_indexers = []
            for indexer in indexers:
                formatted_indexers.append({
                    "value": indexer.get("id"),
                    "text": indexer.get("name")
                })
            
            return {"code": 0, "data": formatted_indexers}
        except Exception as e:
            return {"code": 1, "message": f"获取索引器异常: {str(e)}"}

    def get_state(self) -> bool:
        """
        获取插件状态
        """
        # 确保返回明确的布尔值
        state = bool(self._enabled and self._host and self._api_key)
        print(f"【{self.plugin_name}】get_state返回: {state}, enabled={self._enabled}, host={bool(self._host)}, api_key={bool(self._api_key)}")
        return state

    def stop_service(self) -> None:
        """
        停止插件服务
        """
        print(f"【{self.plugin_name}】停止插件服务...")
        self._remove_jackett_indexers()

    def get_service(self) -> List[Dict[str, Any]]:
        """
        注册定时服务
        """
        return [{
            "id": "jackett_update_indexers",
            "name": "更新Jackett索引器",
            "trigger": "interval",
            "func": self._add_jackett_indexers,
            "kwargs": {"hours": 12}
        }] 