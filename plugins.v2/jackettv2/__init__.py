from typing import Dict, Any, List, Optional, Tuple
from app.plugins import _PluginBase
from app.utils.http import RequestUtils
import json
import os
import time
import xml.dom.minidom
from urllib.parse import urljoin
import requests

class JackettV2(_PluginBase):
    """
    Jackett V2 搜索器插件 - 专为MoviePilot V2版本设计
    """
    # 插件名称
    plugin_name = "JackettV2"
    # 插件描述
    plugin_desc = "支持 Jackett 搜索器，将Jackett索引器添加到MoviePilot V2内建搜索器中。"
    # 插件图标
    plugin_icon = "https://raw.githubusercontent.com/Jackett/Jackett/master/src/Jackett.Common/Content/favicon.ico"
    # 插件版本
    plugin_version = "1.0"
    # 插件作者
    plugin_author = "lightolly"
    # 作者主页
    author_url = "https://github.com/lightolly"
    # 插件配置项ID前缀
    plugin_config_prefix = "jackettv2_"
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
        
        # 如果配置了API信息，则尝试添加索引器，即使插件未启用
        if self._host and self._api_key:
            print(f"【{self.plugin_name}】尝试添加Jackett索引器...")
            try:
                self._add_jackett_indexers()
            except Exception as e:
                print(f"【{self.plugin_name}】添加索引器异常: {str(e)}")
                import traceback
                print(f"【{self.plugin_name}】异常详情: {traceback.format_exc()}")

    def get_state(self) -> bool:
        """
        获取插件状态
        """
        state = bool(self._enabled and self._host and self._api_key)
        print(f"【{self.plugin_name}】get_state返回: {state}, enabled={self._enabled}, host={bool(self._host)}, api_key={bool(self._api_key)}")
        return state

    def get_form(self) -> Tuple[List[dict], dict]:
        """
        获取配置表单
        """
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
                }
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
        return [
            {
                'component': 'VAlert',
                'props': {
                    'type': 'info',
                    'text': '此插件用于对接Jackett搜索器，将Jackett中配置的索引器添加到MoviePilot的内建索引中。需要先在Jackett中添加并配置好索引器，启用插件并保存配置后，即可在搜索中使用这些索引器。',
                    'class': 'mb-4'
                }
            }
        ]

    def get_api(self) -> List[dict]:
        """
        获取API接口
        """
        return [
            {
                "path": "/jackettv2/indexers",
                "endpoint": self.get_indexers,
                "methods": ["GET"],
                "summary": "获取Jackett索引器列表",
                "description": "获取已配置的Jackett索引器列表"
            },
            {
                "path": "/jackettv2/reload",
                "endpoint": self.reload_indexers,
                "methods": ["GET"],
                "summary": "重新加载Jackett索引器",
                "description": "重新加载Jackett索引器到MoviePilot"
            }
        ]

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
            # 设置请求头
            headers = {
                "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                "User-Agent": "MoviePilot/2.0",
                "X-Api-Key": self._api_key,
                "Accept": "application/json, text/javascript, */*; q=0.01"
            }
            
            # 创建session并设置headers
            session = requests.session()
            req = RequestUtils(headers=headers, session=session)
            
            # 如果设置了密码，则进行认证
            if self._password:
                dashboard_url = f"{self._host}/UI/Dashboard"
                auth_data = {"password": self._password}
                auth_params = {"password": self._password}
                
                dashboard_res = req.post_res(
                    url=dashboard_url,
                    data=auth_data,
                    params=auth_params
                )
                
                if dashboard_res and session.cookies:
                    self._cookies = session.cookies.get_dict()
            
            # 获取索引器列表
            indexer_query_url = f"{self._host}/api/v2.0/indexers?configured=true"
            response = req.get_res(
                url=indexer_query_url,
                verify=False
            )
            
            if response and response.status_code == 200:
                indexers = response.json()
                if indexers and isinstance(indexers, list):
                    print(f"【{self.plugin_name}】成功获取到{len(indexers)}个索引器")
                    return indexers
                    
            return []
                
        except Exception as e:
            print(f"【{self.plugin_name}】获取Jackett索引器异常: {str(e)}")
            return []

    def _format_indexer(self, jackett_indexer):
        """
        将Jackett索引器格式化为MoviePilot V2索引器格式
        """
        try:
            # 从Jackett API返回的数据中提取必要信息
            indexer_id = jackett_indexer.get("id", "")
            indexer_name = jackett_indexer.get("name", "")
            
            # 添加分类信息
            categories = {
                "movie": [
                    {"id": "2000", "desc": "Movies"}, 
                    {"id": "2010", "desc": "Movies/Foreign"},
                    {"id": "2020", "desc": "Movies/BluRay"}, 
                    {"id": "2030", "desc": "Movies/DVD"},
                    {"id": "2040", "desc": "Movies/HD"}, 
                    {"id": "2045", "desc": "Movies/UHD"},
                    {"id": "2050", "desc": "Movies/3D"}, 
                    {"id": "2060", "desc": "Movies/SD"}
                ],
                "tv": [
                    {"id": "5000", "desc": "TV"}, 
                    {"id": "5020", "desc": "TV/Blu-ray"},
                    {"id": "5030", "desc": "TV/DVD"}, 
                    {"id": "5040", "desc": "TV/HD"},
                    {"id": "5050", "desc": "TV/SD"}, 
                    {"id": "5060", "desc": "TV/Foreign"},
                    {"id": "5070", "desc": "TV/Sport"}
                ]
            }
            
            # 使用符合MoviePilot V2要求的索引器格式
            mp_indexer = {
                "id": f"jackett_{indexer_id.lower()}",
                "name": f"[Jackett] {indexer_name}",
                "domain": self._host,
                "url": self._host,
                "encoding": "UTF-8",
                "public": True,
                "proxy": True,
                "language": "zh_CN",
                "category": categories,
                "builtin": False,
                "search": {
                    "paths": [
                        {
                            "path": f"/api/v2.0/indexers/{indexer_id}/results/torznab",
                            "method": "get"
                        }
                    ],
                    "params": {
                        "t": "search",
                        "q": "{keyword}",
                        "cat": "{cat}",
                        "apikey": self._api_key
                    }
                },
                "torrents": {
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
                            "selector": "guid"
                        },
                        "download": {
                            "selector": "link"
                        },
                        "size": {
                            "selector": "size"
                        },
                        "date_added": {
                            "selector": "pubDate",
                            "optional": True
                        },
                        "seeders": {
                            "selector": "torznab|attr[name=seeders]",
                            "default": "0"
                        },
                        "leechers": {
                            "selector": "torznab|attr[name=peers]",
                            "default": "0"
                        },
                        "downloadvolumefactor": {
                            "case": {
                                "*": 0
                            }
                        },
                        "uploadvolumefactor": {
                            "case": {
                                "*": 1
                            }
                        }
                    }
                }
            }
            
            print(f"【{self.plugin_name}】已格式化索引器: {indexer_name}")
            return mp_indexer
        except Exception as e:
            print(f"【{self.plugin_name}】格式化索引器失败: {str(e)}")
            return None

    def _add_jackett_indexers(self):
        """
        添加Jackett索引器到MoviePilot V2内建索引器
        """
        try:
            # 导入SitesHelper
            from app.helper.sites import SitesHelper
            sites_helper = SitesHelper()
            
            # 获取Jackett索引器列表
            indexers = self._fetch_jackett_indexers()
            if not indexers:
                print(f"【{self.plugin_name}】未获取到Jackett索引器")
                return
            
            print(f"【{self.plugin_name}】获取到{len(indexers)}个Jackett索引器")
            
            # 先移除已添加的索引器
            self._remove_jackett_indexers()
            
            # 清空已添加索引器列表
            self._added_indexers = []
            
            # 添加索引器
            for indexer in indexers:
                indexer_id = indexer.get("id")
                if not indexer_id:
                    continue
                    
                if self._indexers and indexer_id not in self._indexers:
                    print(f"【{self.plugin_name}】跳过未选择的索引器: {indexer.get('name')}")
                    continue
                
                domain = f"jackett_{indexer_id.lower()}"
                
                # 格式化为MoviePilot支持的格式
                mp_indexer = self._format_indexer(indexer)
                if not mp_indexer:
                    continue
                    
                try:
                    # 添加到MoviePilot
                    sites_helper.add_indexer(domain=domain, indexer=mp_indexer)
                    self._added_indexers.append(domain)
                    print(f"【{self.plugin_name}】成功添加索引器: {indexer.get('name')}")
                except Exception as e:
                    print(f"【{self.plugin_name}】添加索引器失败: {indexer.get('name')} - {str(e)}")
            
            print(f"【{self.plugin_name}】共添加了{len(self._added_indexers)}个索引器")
            
            # 刷新索引器
            sites_helper.init_indexer()
            
        except Exception as e:
            print(f"【{self.plugin_name}】添加Jackett索引器异常: {str(e)}")

    def _remove_jackett_indexers(self):
        """
        从MoviePilot V2中移除Jackett索引器
        """
        try:
            from app.helper.sites import SitesHelper
            sites_helper = SitesHelper()
            
            # 移除已添加的索引器
            removed_count = 0
            for domain in self._added_indexers:
                try:
                    sites_helper.remove_indexer(domain=domain)
                    removed_count += 1
                    print(f"【{self.plugin_name}】成功移除索引器: {domain}")
                except Exception as e:
                    print(f"【{self.plugin_name}】移除索引器失败: {domain} - {str(e)}")
                    
            # 清空已添加索引器列表
            self._added_indexers = []
            print(f"【{self.plugin_name}】共移除了 {removed_count} 个索引器")
            
        except Exception as e:
            print(f"【{self.plugin_name}】移除Jackett索引器异常: {str(e)}")

    def get_indexers(self):
        """
        获取索引器列表
        """
        if not self._host or not self._api_key:
            return {"code": 1, "message": "请先配置Jackett地址和API Key"}
        
        try:
            # 获取Jackett索引器
            indexers = self._fetch_jackett_indexers()
            if not indexers:
                return {"code": 1, "message": "未获取到Jackett索引器"}
            
            # 格式化为选项列表
            formatted_indexers = []
            for indexer in indexers:
                formatted_indexers.append({
                    "value": indexer.get("id"),
                    "text": indexer.get("name")
                })
            
            return {"code": 0, "data": formatted_indexers}
                
        except Exception as e:
            print(f"【{self.plugin_name}】获取索引器异常: {str(e)}")
            return {"code": 1, "message": f"获取索引器异常: {str(e)}"}

    def reload_indexers(self):
        """
        重新加载索引器
        """
        if not self._host or not self._api_key:
            return {"code": 1, "message": "请先配置Jackett地址和API Key"}
            
        try:
            # 强制启用插件功能
            self._enabled = True
            
            # 重新添加索引器
            self._add_jackett_indexers()
            
            return {"code": 0, "message": f"重新加载索引器成功，共添加{len(self._added_indexers)}个索引器"}
                
        except Exception as e:
            print(f"【{self.plugin_name}】重新加载索引器异常: {str(e)}")
            return {"code": 1, "message": f"重新加载索引器失败: {str(e)}"}

    def stop_service(self) -> None:
        """
        停止插件服务
        """
        try:
            print(f"【{self.plugin_name}】正在停止插件服务...")
            # 移除所有添加的索引器
            self._remove_jackett_indexers()
            # 清理会话
            self._session = None
            self._cookies = None
            print(f"【{self.plugin_name}】插件服务已停止")
        except Exception as e:
            print(f"【{self.plugin_name}】停止插件服务出错: {str(e)}")

    def get_service(self) -> List[Dict[str, Any]]:
        """
        注册定时服务
        """
        return [{
            "id": "jackettv2_update_indexers",
            "name": "更新Jackett索引器",
            "trigger": "interval",
            "func": self._add_jackett_indexers,
            "kwargs": {"hours": 12}
        }] 