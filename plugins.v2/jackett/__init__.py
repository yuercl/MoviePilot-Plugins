from typing import Dict, Any, List, Optional
from app.core.config import settings
from app.core.event import eventmanager, Event
from app.core.event import EventType
from app.plugins import _PluginBase
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
    plugin_version = "1.02"
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
    _indexers = None
    _scheduler = None

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
        self._indexers = config.get("indexers", [])

        # 注册事件
        if self._enabled and self._host and self._api_key:
            self.register_events()

    def get_form(self) -> tuple:
        """
        获取配置表单
        """
        return [
            {
                'component': 'VForm',
                'content': [
                    {
                        'component': 'VRow',
                        'content': [
                            {
                                'component': 'VCol',
                                'props': {
                                    'cols': 12,
                                    'md': 6
                                },
                                'content': [
                                    {
                                        'component': 'VSwitch',
                                        'props': {
                                            'model': 'enabled',
                                            'label': '启用插件'
                                        }
                                    }
                                ]
                            }
                        ]
                    },
                    {
                        'component': 'VRow',
                        'content': [
                            {
                                'component': 'VCol',
                                'props': {
                                    'cols': 12,
                                    'md': 6
                                },
                                'content': [
                                    {
                                        'component': 'VTextField',
                                        'props': {
                                            'model': 'host',
                                            'label': 'Jackett地址',
                                            'placeholder': 'http://localhost:9117'
                                        }
                                    }
                                ]
                            },
                            {
                                'component': 'VCol',
                                'props': {
                                    'cols': 12,
                                    'md': 6
                                },
                                'content': [
                                    {
                                        'component': 'VTextField',
                                        'props': {
                                            'model': 'api_key',
                                            'label': 'API Key',
                                            'type': 'password'
                                        }
                                    }
                                ]
                            }
                        ]
                    },
                    {
                        'component': 'VRow',
                        'content': [
                            {
                                'component': 'VCol',
                                'props': {
                                    'cols': 12
                                },
                                'content': [
                                    {
                                        'component': 'VSelect',
                                        'props': {
                                            'model': 'indexers',
                                            'label': '索引器',
                                            'multiple': True,
                                            'chips': True,
                                            'items': [],
                                            'persistent-hint': True,
                                            'hint': '留空则使用全部索引器'
                                        },
                                        'events': [
                                            {
                                                'name': 'mounted',
                                                'value': 'this.get_indexers'
                                            }
                                        ]
                                    }
                                ]
                            }
                        ]
                    }
                ]
            }
        ], {
            "enabled": False,
            "host": "",
            "api_key": "",
            "indexers": []
        }

    def get_page(self) -> List[dict]:
        """
        获取页面
        """
        return [
            {
                'component': 'VRow',
                'content': [
                    {
                        'component': 'VCol',
                        'props': {
                            'cols': 12
                        },
                        'content': [
                            {
                                'component': 'VAlert',
                                'props': {
                                    'type': 'info',
                                    'text': '此插件用于对接Jackett搜索器，实现资源检索功能。'
                                }
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
        return [
            {
                "path": "/jackett/indexers",
                "endpoint": self.get_indexers,
                "methods": ["GET"],
                "summary": "获取Jackett索引器列表",
                "description": "获取已配置的Jackett索引器列表"
            }
        ]

    def get_indexers(self):
        """
        获取索引器列表
        """
        if not self._host or not self._api_key:
            return {"code": 1, "message": "请先配置Jackett"}
        
        try:
            # 使用 Jackett API 获取所有配置的索引器
            response = RequestUtils(content_type="application/json").get_res(
                f"{self._host}/api/v2.0/indexers?configured=true&apikey={self._api_key}"
            )
            if response and response.status_code == 200:
                indexers = []
                for indexer in response.json():
                    indexers.append({
                        "value": indexer["id"],
                        "text": indexer["name"]
                    })
                return {"code": 0, "data": indexers}
            else:
                return {"code": 1, "message": f"获取索引器失败: {response.status_code if response else '无响应'}"}
        except Exception as e:
            return {"code": 1, "message": f"获取索引器异常: {str(e)}"}

    def register_events(self):
        """
        注册事件响应
        """
        @eventmanager.register(EventType.SearchTorrent)
        def search_torrent(event: Event):
            """
            搜索种子
            """
            if not self._enabled:
                return
            
            search_word = event.event_data.get("search_word")
            if not search_word:
                return
            
            try:
                print(f"【{self.plugin_name}】开始搜索: {search_word}")
                
                # 构建搜索URL
                search_url = f"{self._host}/api/v2.0/indexers/all/results?apikey={self._api_key}&Query={search_word}"
                if self._indexers and len(self._indexers) > 0:
                    search_url += f"&Tracker={','.join(self._indexers)}"
                
                # 发送搜索请求
                response = RequestUtils(content_type="application/json").get_res(search_url)
                if not response:
                    print(f"【{self.plugin_name}】搜索请求失败: 无响应")
                    return
                
                if response.status_code != 200:
                    print(f"【{self.plugin_name}】搜索请求失败: HTTP {response.status_code}")
                    return
                
                results = response.json().get("Results", [])
                print(f"【{self.plugin_name}】搜索结果数量: {len(results)}")
                
                # 格式化搜索结果
                formatted_results = []
                for item in results:
                    # 转换为MoviePilot期望的格式
                    formatted_results.append({
                        "title": item.get("Title", ""),
                        "description": item.get("Description", ""),
                        "enclosure": item.get("Link", ""),
                        "size": item.get("Size", 0),
                        "seeders": item.get("Seeders", 0),
                        "peers": item.get("Peers", 0),
                        "page_url": item.get("Details", ""),
                        "indexer": item.get("Tracker", ""),
                        "category": item.get("CategoryDesc", ""),
                        "imdbid": item.get("Imdb", ""),
                    })
                
                # 发送搜索结果事件
                if formatted_results:
                    eventmanager.send_event(EventType.SearchTorrentResult, {
                        "search_word": search_word,
                        "results": formatted_results
                    })
            except Exception as e:
                print(f"【{self.plugin_name}】搜索出错: {str(e)}")

    def get_state(self) -> bool:
        """
        获取插件状态
        """
        return self._enabled and self._host and self._api_key
        
    def stop_service(self) -> None:
        """
        停止插件服务
        """
        try:
            if self._scheduler:
                self._scheduler.remove_all_jobs()
                if self._scheduler.running:
                    self._scheduler.shutdown()
                self._scheduler = None
        except Exception as e:
            print(f"【{self.plugin_name}】停止插件服务出错: {str(e)}") 