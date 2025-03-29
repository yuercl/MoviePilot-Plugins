from typing import Dict, Any, List, Optional, Tuple
from app.plugins import _PluginBase
from app.utils.http import RequestUtils
import json
import os
import time
import xml.dom.minidom
from urllib.parse import urljoin
import requests
import importlib
import yaml

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
    plugin_version = "1.61"
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
        
        # 如果配置了API信息，则尝试添加索引器，即使插件未启用
        if self._host and self._api_key:
            print(f"【{self.plugin_name}】尝试添加Jackett索引器...")
            try:
                self._add_jackett_indexers()
            except Exception as e:
                print(f"【{self.plugin_name}】添加索引器异常: {str(e)}")
                import traceback
                print(f"【{self.plugin_name}】异常详情: {traceback.format_exc()}")

    def _add_jackett_indexers(self):
        """
        添加Jackett索引器到MoviePilot内建索引器
        """
        try:
            # 导入SitesHelper - 尝试多种导入路径
            sites_helper = None
            try:
                # 尝试 V2 版本的导入路径
                from app.helper.sites import SitesHelper
                sites_helper = SitesHelper()
                print(f"【{self.plugin_name}】成功导入SitesHelper (V2路径)")
            except ImportError:
                try:
                    # 尝试 V1 版本的导入路径
                    from app.sites import SitesHelper
                    sites_helper = SitesHelper()
                    print(f"【{self.plugin_name}】成功导入SitesHelper (V1路径)")
                except ImportError as e:
                    print(f"【{self.plugin_name}】导入SitesHelper失败: {str(e)}")
                    return
            
            if not sites_helper:
                print(f"【{self.plugin_name}】无法创建SitesHelper实例")
                return
            
            # 获取Jackett索引器列表
            indexers = self._fetch_jackett_indexers()
            if not indexers:
                print(f"【{self.plugin_name}】未获取到Jackett索引器")
                return
            
            print(f"【{self.plugin_name}】获取到{len(indexers)}个Jackett索引器")
            
            # 先移除已添加的索引器，避免重复
            try:
                self._remove_jackett_indexers()
            except Exception as e:
                print(f"【{self.plugin_name}】移除旧索引器异常: {str(e)}")
            
            # 清空已添加索引器列表
            self._added_indexers = []
            
            # 存储添加的索引器
            new_added = []
            
            # 尝试预先初始化索引器
            try:
                if hasattr(sites_helper, "init_builtin"):
                    print(f"【{self.plugin_name}】尝试初始化内置索引器...")
                    sites_helper.init_builtin()
                if hasattr(sites_helper, "init_indexer"):
                    print(f"【{self.plugin_name}】尝试初始化索引器...")
                    sites_helper.init_indexer()
            except Exception as e:
                print(f"【{self.plugin_name}】初始化索引器异常: {str(e)}")
            
            for indexer in indexers:
                indexer_id = indexer.get("id")
                if not indexer_id:
                    continue
                    
                if self._indexers and indexer_id not in self._indexers:
                    print(f"【{self.plugin_name}】跳过未选择的索引器: {indexer.get('name')}")
                    continue
                
                domain = f"jackett_{indexer_id.lower()}"  # 确保使用小写的ID
                
                # 格式化为MoviePilot支持的格式
                mp_indexer = self._format_indexer(indexer)
                if not mp_indexer:
                    continue
                    
                # 添加到MoviePilot
                try:
                    # 先检查索引器是否已存在
                    existing_sites = []
                    if hasattr(sites_helper, "get_indexers"):
                        existing_sites = sites_helper.get_indexers() or []
                    elif hasattr(sites_helper, "get_all_indexers"):
                        existing_sites = sites_helper.get_all_indexers() or []
                    
                    if isinstance(existing_sites, dict):
                        existing_keys = existing_sites.keys()
                        exists = domain in existing_keys
                    else:
                        exists = domain in existing_sites
                    
                    if exists:
                        print(f"【{self.plugin_name}】索引器已存在，先移除: {domain}")
                        try:
                            if hasattr(sites_helper, "remove_indexer"):
                                sites_helper.remove_indexer(domain=domain)
                            elif hasattr(sites_helper, "delete_indexer"):
                                sites_helper.delete_indexer(domain=domain)
                        except Exception as e:
                            print(f"【{self.plugin_name}】移除已存在索引器失败: {str(e)}")
                    
                    # 添加索引器前进行必要准备
                    print(f"【{self.plugin_name}】尝试添加索引器: {indexer.get('name')} -> {domain}")
                    
                    # 注册索引器到系统
                    try:
                        # 先尝试直接添加
                        sites_helper.add_indexer(domain=domain, indexer=mp_indexer)
                        
                        # 尝试其他可能的注册方法
                        if hasattr(sites_helper, "register_indexer"):
                            sites_helper.register_indexer(domain=domain, url=self._host)
                        
                        # 添加到成功列表
                        self._added_indexers.append(domain)
                        new_added.append(domain)
                        print(f"【{self.plugin_name}】成功添加索引器: {indexer.get('name')} -> {domain}")
                    except Exception as e:
                        print(f"【{self.plugin_name}】添加索引器失败: {indexer.get('name')} - {str(e)}")
                        import traceback
                        print(f"【{self.plugin_name}】添加索引器异常详情: {traceback.format_exc()}")
                except Exception as e:
                    print(f"【{self.plugin_name}】添加索引器失败: {indexer.get('name')} - {str(e)}")
            
            print(f"【{self.plugin_name}】本次新增{len(new_added)}个索引器，共加入{len(self._added_indexers)}个索引器")
            
            # 尝试直接激活索引器，这是关键的一步
            try:
                # 尝试多种可能的刷新/初始化方法
                print(f"【{self.plugin_name}】尝试多种方法激活索引器...")
                
                # 尝试直接写入系统配置
                try:
                    from app.db.systemconfig_oper import SystemConfigOper
                    from app.schemas.types import SystemConfigKey
                    
                    print(f"【{self.plugin_name}】尝试直接写入系统配置...")
                    
                    # 获取当前索引器配置 - 兼容不同版本
                    config_oper = SystemConfigOper()
                    indexers_config = {}
                    
                    # 尝试不同的配置键名
                    try:
                        # 尝试V2版本键名
                        if hasattr(SystemConfigKey, "UserIndexer"):
                            indexers_config = config_oper.get(SystemConfigKey.UserIndexer) or {}
                            print(f"【{self.plugin_name}】使用SystemConfigKey.UserIndexer获取配置")
                        # 尝试其他可能的键名
                        elif hasattr(SystemConfigKey, "INDEXER"):
                            indexers_config = config_oper.get(SystemConfigKey.INDEXER) or {}
                            print(f"【{self.plugin_name}】使用SystemConfigKey.INDEXER获取配置")
                        elif hasattr(SystemConfigKey, "Indexer"):
                            indexers_config = config_oper.get(SystemConfigKey.Indexer) or {}
                            print(f"【{self.plugin_name}】使用SystemConfigKey.Indexer获取配置")
                        else:
                            # 尝试使用字符串直接访问
                            for possible_key in ["UserIndexer", "INDEXER", "Indexer", "indexer"]:
                                try:
                                    indexers_config = config_oper.get(possible_key) or {}
                                    if indexers_config:
                                        print(f"【{self.plugin_name}】使用字符串键'{possible_key}'成功获取配置")
                                        break
                                except Exception:
                                    continue
                    except Exception as e:
                        print(f"【{self.plugin_name}】获取系统配置异常: {str(e)}")
                        indexers_config = {}
                    
                    print(f"【{self.plugin_name}】当前系统索引器配置: {len(indexers_config)} 个索引器")
                    
                    # 将新索引器添加到配置中
                    indexer_count = 0
                    for domain in self._added_indexers:
                        # 获取索引器配置
                        indexer_info = None
                        for indexer in indexers:
                            formatted = self._format_indexer(indexer)
                            if formatted and formatted.get("id", "").lower() == domain.lower():
                                indexer_info = formatted
                                break
                        
                        if indexer_info:
                            # 添加到配置中
                            indexers_config[domain] = indexer_info
                            indexer_count += 1
                            print(f"【{self.plugin_name}】直接添加索引器到系统配置: {domain}")
                    
                    # 保存配置
                    if indexer_count > 0:
                        # 尝试不同的配置键名来保存
                        save_success = False
                        
                        try:
                            if hasattr(SystemConfigKey, "UserIndexer"):
                                config_oper.set(SystemConfigKey.UserIndexer, indexers_config)
                                save_success = True
                                print(f"【{self.plugin_name}】使用SystemConfigKey.UserIndexer保存配置")
                            elif hasattr(SystemConfigKey, "INDEXER"):
                                config_oper.set(SystemConfigKey.INDEXER, indexers_config)
                                save_success = True
                                print(f"【{self.plugin_name}】使用SystemConfigKey.INDEXER保存配置")
                            elif hasattr(SystemConfigKey, "Indexer"):
                                config_oper.set(SystemConfigKey.Indexer, indexers_config)
                                save_success = True
                                print(f"【{self.plugin_name}】使用SystemConfigKey.Indexer保存配置")
                            else:
                                # 尝试使用字符串直接保存
                                for possible_key in ["UserIndexer", "INDEXER", "Indexer", "indexer"]:
                                    try:
                                        config_oper.set(possible_key, indexers_config)
                                        save_success = True
                                        print(f"【{self.plugin_name}】使用字符串键'{possible_key}'成功保存配置")
                                        break
                                    except Exception:
                                        continue
                        except Exception as e:
                            print(f"【{self.plugin_name}】保存配置异常: {str(e)}")
                            
                        if save_success:
                            print(f"【{self.plugin_name}】成功保存 {indexer_count} 个索引器到系统配置")
                        else:
                            print(f"【{self.plugin_name}】尝试了所有可能的配置键，仍无法保存索引器配置")
                    
                    # 尝试触发配置重载
                    try:
                        # 尝试直接调用站点服务刷新
                        try:
                            from app.services.indexer import IndexerService
                            print(f"【{self.plugin_name}】尝试直接调用站点服务刷新...")
                            indexer_service = IndexerService()
                            
                            # 尝试不同的刷新方法
                            if hasattr(indexer_service, "init_builtin"):
                                indexer_service.init_builtin()
                                print(f"【{self.plugin_name}】成功调用站点服务init_builtin方法")
                            
                            if hasattr(indexer_service, "init_indexer"):
                                indexer_service.init_indexer()
                                print(f"【{self.plugin_name}】成功调用站点服务init_indexer方法")
                            
                            if hasattr(indexer_service, "refresh"):
                                indexer_service.refresh()
                                print(f"【{self.plugin_name}】成功调用站点服务refresh方法")
                            
                            print(f"【{self.plugin_name}】站点服务刷新完成")
                        except Exception as e:
                            print(f"【{self.plugin_name}】直接调用站点服务刷新失败: {str(e)}")
                            import traceback
                            print(f"【{self.plugin_name}】刷新异常详情: {traceback.format_exc()}")
                        
                        # 尝试发送模块重载事件
                        from app.helper.event import EventManager
                        from app.schemas.types import EventType
                        
                        print(f"【{self.plugin_name}】尝试发送模块重载事件...")
                        event_manager = EventManager()
                        event_manager.send_event(EventType.ModuleReload)
                        print(f"【{self.plugin_name}】模块重载事件已发送")
                        
                        # 尝试发送站点刷新事件
                        event_manager.send_event(EventType.SiteRefreshed)
                        print(f"【{self.plugin_name}】站点刷新事件已发送")
                    except Exception as e:
                        print(f"【{self.plugin_name}】发送模块重载事件失败: {str(e)}")
                    
                    # 检查是否有 refresh_indexer 方法
                    if hasattr(sites_helper, "refresh_indexer"):
                        print(f"【{self.plugin_name}】尝试刷新索引器列表...")
                        sites_helper.refresh_indexer()
                        print(f"【{self.plugin_name}】索引器列表刷新完成")
                    else:
                        print(f"【{self.plugin_name}】SitesHelper 没有 refresh_indexer 方法")
                    
                    # 检查是否有 init_indexer 方法
                    if hasattr(sites_helper, "init_indexer"):
                        print(f"【{self.plugin_name}】尝试初始化索引器...")
                        sites_helper.init_indexer()
                        print(f"【{self.plugin_name}】索引器初始化完成")
                    else:
                        print(f"【{self.plugin_name}】SitesHelper 没有 init_indexer 方法")
                    
                    # 尝试其他可能的激活方法
                    if hasattr(sites_helper, "init"):
                        print(f"【{self.plugin_name}】尝试调用init方法...")
                        sites_helper.init()
                    
                    if hasattr(sites_helper, "init_builtin"):
                        print(f"【{self.plugin_name}】尝试初始化内置索引器...")
                        sites_helper.init_builtin()
                    
                    if hasattr(sites_helper, "refresh"):
                        print(f"【{self.plugin_name}】尝试调用refresh方法...")
                        sites_helper.refresh()
                    
                    # 尝试重新加载配置
                    if hasattr(sites_helper, "load_config"):
                        print(f"【{self.plugin_name}】尝试重新加载配置...")
                        sites_helper.load_config()
                    
                    # 强制刷新缓存
                    if hasattr(sites_helper, "clear_cache"):
                        print(f"【{self.plugin_name}】尝试清除缓存...")
                        sites_helper.clear_cache()
                    
                    # 尝试发送刷新事件
                    try:
                        # 尝试直接调用站点服务刷新
                        try:
                            from app.services.indexer import IndexerService
                            print(f"【{self.plugin_name}】尝试直接调用站点服务刷新...")
                            indexer_service = IndexerService()
                            
                            # 尝试不同的刷新方法
                            if hasattr(indexer_service, "init_builtin"):
                                indexer_service.init_builtin()
                                print(f"【{self.plugin_name}】成功调用站点服务init_builtin方法")
                            
                            if hasattr(indexer_service, "init_indexer"):
                                indexer_service.init_indexer()
                                print(f"【{self.plugin_name}】成功调用站点服务init_indexer方法")
                            
                            if hasattr(indexer_service, "refresh"):
                                indexer_service.refresh()
                                print(f"【{self.plugin_name}】成功调用站点服务refresh方法")
                            
                            print(f"【{self.plugin_name}】站点服务刷新完成")
                        except Exception as e:
                            print(f"【{self.plugin_name}】直接调用站点服务刷新失败: {str(e)}")
                            import traceback
                            print(f"【{self.plugin_name}】刷新异常详情: {traceback.format_exc()}")
                        
                        # 尝试发送模块重载事件
                        from app.helper.event import EventManager
                        from app.schemas.types import EventType
                        EventManager().send_event(EventType.ModuleReload)
                        print(f"【{self.plugin_name}】成功发送模块重载事件")
                        
                        # 尝试发送站点刷新事件
                        EventManager().send_event(EventType.SiteRefreshed)
                        print(f"【{self.plugin_name}】成功发送站点刷新事件")
                    except Exception as e:
                        print(f"【{self.plugin_name}】发送刷新事件失败: {str(e)}")
                    
                    # 直接获取所有站点检查是否添加成功
                    sites = None
                    if hasattr(sites_helper, "get_indexers"):
                        sites = sites_helper.get_indexers()
                    elif hasattr(sites_helper, "get_all_indexers"):
                        sites = sites_helper.get_all_indexers()
                    
                    if sites:
                        # 检查sites是列表还是字典，并相应地处理
                        if isinstance(sites, dict):
                            jackett_sites = [s for s in sites.keys() if isinstance(s, str) and s.startswith("jackett_")]
                        else:
                            jackett_sites = [s for s in sites if isinstance(s, str) and s.startswith("jackett_")]
                        
                        print(f"【{self.plugin_name}】系统当前共有 {len(jackett_sites)} 个 Jackett 索引器: {jackett_sites}")
                    else:
                        print(f"【{self.plugin_name}】无法获取系统索引器列表")
                    
                    # 如果直接写入配置后发现索引器仍然为0，尝试触发系统直接重载
                    if not jackett_sites or len(jackett_sites) == 0:
                        print(f"【{self.plugin_name}】使用配置保存成功但索引器未激活，尝试执行系统重启操作...")
                        try:
                            # 尝试找到并调用系统重启接口
                            for module_path in [
                                "app.app", 
                                "app.core.config", 
                                "app.core.module", 
                                "app.utils.system"
                            ]:
                                try:
                                    module = importlib.import_module(module_path)
                                    if hasattr(module, "restart") and callable(module.restart):
                                        print(f"【{self.plugin_name}】找到系统重启方法: {module_path}.restart")
                                        module.restart()
                                        print(f"【{self.plugin_name}】已触发系统重启")
                                        break
                                    elif hasattr(module, "reboot") and callable(module.reboot):
                                        print(f"【{self.plugin_name}】找到系统重启方法: {module_path}.reboot")
                                        module.reboot()
                                        print(f"【{self.plugin_name}】已触发系统重启")
                                        break
                                except (ImportError, AttributeError):
                                    continue
                        
                            # 如果没有找到重启方法，尝试修改系统配置强制重新加载
                            print(f"【{self.plugin_name}】尝试调整系统配置文件以触发重载...")
                            
                            try:
                                import os
                                import json
                                
                                # 尝试找到配置文件位置
                                config_paths = [
                                    "/config/user.yaml",
                                    "/config/config.yaml",
                                    "/app/config/user.yaml",
                                    "/app/config/config.yaml"
                                ]
                                
                                for config_path in config_paths:
                                    if os.path.exists(config_path):
                                        print(f"【{self.plugin_name}】找到配置文件: {config_path}")
                                        # 修改配置文件的访问时间，可能触发系统监测到配置变化
                                        try:
                                            # 更新文件的访问和修改时间到当前时间
                                            os.utime(config_path, None)
                                            print(f"【{self.plugin_name}】已更新配置文件时间戳")
                                        except Exception as e:
                                            print(f"【{self.plugin_name}】更新配置文件时间戳失败: {str(e)}")
                                        break
                            except Exception as e:
                                print(f"【{self.plugin_name}】尝试修改配置文件失败: {str(e)}")
                            
                            print(f"【{self.plugin_name}】强制激活操作完成，请重新检查索引器状态")
                        except Exception as e:
                            print(f"【{self.plugin_name}】尝试系统重载失败: {str(e)}")
                    
                except Exception as e:
                    print(f"【{self.plugin_name}】尝试刷新索引器异常: {str(e)}")
                    # 打印异常的详细堆栈信息，帮助调试
                    import traceback
                    print(f"【{self.plugin_name}】异常详情: {traceback.format_exc()}")
                
            except Exception as e:
                print(f"【{self.plugin_name}】尝试刷新索引器异常: {str(e)}")
                # 打印异常的详细堆栈信息，帮助调试
                import traceback
                print(f"【{self.plugin_name}】异常详情: {traceback.format_exc()}")
            
        except Exception as e:
            print(f"【{self.plugin_name}】添加Jackett索引器异常: {str(e)}")
    
    def _fetch_jackett_indexers(self):
        """
        获取Jackett索引器列表，支持重试机制
        """
        if not self._host or not self._api_key:
            print(f"【{self.plugin_name}】缺少必要配置参数，无法获取索引器")
            return []
        
        # 规范化host地址
        if self._host.endswith('/'):
            self._host = self._host[:-1]
            
        # 设置重试参数
        max_retries = 3
        retry_interval = 5
        current_try = 1
            
        try:
            # 设置请求头
            headers = {
                "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                "User-Agent": "MoviePilot/1.0",
                "X-Api-Key": self._api_key,
                "Accept": "application/json, text/javascript, */*; q=0.01"
            }
            
            print(f"【{self.plugin_name}】请求头: {headers}")
            
            # 创建session并设置headers
            session = requests.session()
            req = RequestUtils(headers=headers, session=session)
            
            # 如果设置了密码，则进行认证
            if self._password:
                dashboard_url = f"{self._host}/UI/Dashboard"
                print(f"【{self.plugin_name}】尝试访问Dashboard进行认证: {dashboard_url}")
                
                auth_data = {"password": self._password}
                auth_params = {"password": self._password}
                
                dashboard_res = req.post_res(
                    url=dashboard_url,
                    data=auth_data,
                    params=auth_params
                )
                
                if dashboard_res and session.cookies:
                    self._cookies = session.cookies.get_dict()
                    print(f"【{self.plugin_name}】成功获取Cookie: {self._cookies}")
                else:
                    print(f"【{self.plugin_name}】获取Cookie失败")
            
            # 重置重试计数
            current_try = 1
            
            # 获取索引器列表 - 添加重试机制
            while current_try <= max_retries:
                try:
                    # 使用正确的API路径
                    indexer_query_url = f"{self._host}/api/v2.0/indexers?configured=true"
                    print(f"【{self.plugin_name}】请求索引器列表 (第{current_try}次尝试): {indexer_query_url}")
                    
                    # 请求API
                    response = req.get_res(
                        url=indexer_query_url,
                        verify=False
                    )
                    
                    if response:
                        print(f"【{self.plugin_name}】收到响应: HTTP {response.status_code}")
                        print(f"【{self.plugin_name}】响应头: {dict(response.headers)}")
                        
                        if response.status_code == 200:
                            try:
                                # 尝试解析JSON
                                indexers = response.json()
                                if indexers and isinstance(indexers, list):
                                    print(f"【{self.plugin_name}】成功获取到{len(indexers)}个索引器")
                                    return indexers
                                else:
                                    print(f"【{self.plugin_name}】解析索引器列表失败: 无效的JSON响应")
                            except Exception as e:
                                print(f"【{self.plugin_name}】解析索引器列表JSON异常: {str(e)}")
                                print(f"【{self.plugin_name}】响应内容: {response.text[:500]}...")
                        elif response.status_code == 401:
                            print(f"【{self.plugin_name}】认证失败，请检查API Key是否正确")
                            break
                        elif response.status_code == 403:
                            print(f"【{self.plugin_name}】访问被拒绝，请检查Jackett配置")
                            break
                        else:
                            print(f"【{self.plugin_name}】获取索引器列表失败: HTTP {response.status_code}")
                            if response and hasattr(response, 'text'):
                                print(f"【{self.plugin_name}】响应内容: {response.text[:500]}...")
                    else:
                        print(f"【{self.plugin_name}】获取索引器列表失败: 无响应")
                    
                    if current_try < max_retries:
                        print(f"【{self.plugin_name}】{retry_interval}秒后进行第{current_try + 1}次重试...")
                        time.sleep(retry_interval)
                    current_try += 1
                    
                except Exception as e:
                    print(f"【{self.plugin_name}】请求索引器列表异常: {str(e)}")
                    if current_try < max_retries:
                        print(f"【{self.plugin_name}】{retry_interval}秒后进行第{current_try + 1}次重试...")
                        time.sleep(retry_interval)
                    current_try += 1
            
            print(f"【{self.plugin_name}】在{max_retries}次尝试后仍未能获取索引器列表")
            return []
                
        except Exception as e:
            print(f"【{self.plugin_name}】获取Jackett索引器异常: {str(e)}")
            return []
    
    def _format_indexer(self, jackett_indexer):
        """
        将Jackett索引器格式化为MoviePilot索引器格式
        """
        try:
            # 从Jackett API返回的数据中提取必要信息
            indexer_id = jackett_indexer.get("id", "")
            indexer_name = jackett_indexer.get("name", "")
            
            # 使用最简单的索引器格式，只包含MoviePilot必须的字段
            mp_indexer = {
                "id": f"jackett_{indexer_id.lower()}",
                "name": f"[Jackett] {indexer_name}",
                "domain": self._host,
                "url": self._host,
                "encoding": "UTF-8",
                "public": True,
                "proxy": True,
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
                        "apikey": self._api_key
                    }
                },
                "torrents": {
                    "list": {
                        "selector": "item"
                    },
                    "fields": {
                        "title": {
                            "selector": "title"
                        },
                        "download": {
                            "selector": "link"
                        },
                        "size": {
                            "selector": "size"
                        },
                        "seeders": {
                            "selector": "torznab|attr[name=seeders]",
                            "default": "0"
                        },
                        "leechers": {
                            "selector": "torznab|attr[name=peers]",
                            "default": "0"
                        }
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
                'component': 'VRow',
                'content': [
                    {
                        'component': 'VCol',
                        'props': {
                            'cols': 6
                        },
                        'content': [
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
                                        'value': 'this.refreshIndexers()'
                                    }
                                ]
                            }
                        ]
                    },
                    {
                        'component': 'VCol',
                        'props': {
                            'cols': 6
                        },
                        'content': [
                            {
                                'component': 'VBtn',
                                'props': {
                                    'color': 'success',
                                    'block': True,
                                    'class': 'mb-4'
                                },
                                'text': '重新加载索引器到搜索系统',
                                'events': [
                                    {
                                        'name': 'click',
                                        'value': 'this.reloadIndexers()'
                                    }
                                ]
                            }
                        ]
                    }
                ]
            },
            {
                'component': 'VAlert',
                'props': {
                    'type': 'warning',
                    'text': '如果索引器列表为空，请检查Jackett配置是否正确。如果列表有内容但搜索时无法使用，请点击"重新加载索引器到搜索系统"按钮。',
                    'class': 'mb-4'
                }
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
                        'component': 'VCardText',
                        'content': [
                            {
                                'component': 'VAlert',
                                'props': {
                                    'type': 'info',
                                    'class': 'mb-4',
                                    'model': 'indexerStatus',
                                    'outlined': True,
                                    'border': 'left'
                                },
                                'text': '索引器状态: {{indexerStatus}}',
                                'events': [
                                    {
                                        'name': 'mounted',
                                        'value': 'this.checkIndexerStatus()'
                                    }
                                ]
                            }
                        ]
                    },
                    {
                        'component': 'VDataTable',
                        'props': {
                            'headers': [
                                {'text': 'ID', 'value': 'id'},
                                {'text': '索引器名称', 'value': 'name'},
                                {'text': '状态', 'value': 'status'}
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
                                'value': 'this.loadIndexers()'
                            }
                        ]
                    }
                ]
            },
            {
                'component': 'VScript',
                'content': '''
                    export default {
                        data() {
                            return {
                                items: [],
                                loading: false,
                                systemIndexers: [],
                                indexerStatus: "未知"
                            }
                        },
                        methods: {
                            // 刷新Jackett索引器列表
                            refreshIndexers() {
                                this.loading = true;
                                this.$axios.get("/api/v1/plugin/jackett/indexers")
                                    .then(res => {
                                        if (res.data.code === 0) {
                                            this.items = res.data.data.map(item => ({
                                                id: item.value,
                                                name: item.text,
                                                status: this.getIndexerStatus(item.value)
                                            }));
                                            
                                            // 更新系统索引器列表
                                            if (res.data.system_indexers) {
                                                this.systemIndexers = res.data.system_indexers;
                                                this.updateIndexerStatus();
                                            }
                                            
                                            this.$toast.success("索引器列表刷新成功");
                                        } else {
                                            this.$toast.error(res.data.message || "获取索引器列表失败");
                                        }
                                    })
                                    .catch(err => {
                                        this.$toast.error("获取索引器列表异常: " + err);
                                    })
                                    .finally(() => {
                                        this.loading = false;
                                    });
                            },
                            
                            // 重新加载索引器到搜索系统
                            reloadIndexers() {
                                this.loading = true;
                                this.$axios.get("/api/v1/plugin/jackett/reload")
                                    .then(res => {
                                        if (res.data.code === 0) {
                                            this.$toast.success(res.data.message);
                                            // 重新加载索引器列表
                                            this.refreshIndexers();
                                        } else {
                                            this.$toast.error(res.data.message);
                                        }
                                    })
                                    .catch(err => {
                                        this.$toast.error("重新加载索引器异常: " + err);
                                    })
                                    .finally(() => {
                                        this.loading = false;
                                    });
                            },
                            
                            // 加载索引器列表
                            loadIndexers() {
                                this.refreshIndexers();
                            },
                            
                            // 检查索引器状态
                            checkIndexerStatus() {
                                this.$axios.get("/api/v1/plugin/jackett/indexers")
                                    .then(res => {
                                        if (res.data.code === 0) {
                                            if (res.data.system_indexers) {
                                                this.systemIndexers = res.data.system_indexers;
                                                this.updateIndexerStatus();
                                            } else {
                                                this.indexerStatus = "无法获取索引器状态信息";
                                            }
                                        } else {
                                            this.indexerStatus = "获取索引器状态失败: " + (res.data.message || "未知错误");
                                        }
                                    })
                                    .catch(err => {
                                        this.indexerStatus = "检查索引器状态异常: " + err;
                                    });
                            },
                            
                            // 更新索引器状态信息
                            updateIndexerStatus() {
                                if (this.systemIndexers && this.systemIndexers.length > 0) {
                                    this.indexerStatus = `系统中已添加 ${this.systemIndexers.length} 个 Jackett 索引器`;
                                } else {
                                    this.indexerStatus = "系统中暂无 Jackett 索引器，请点击"重新加载索引器到搜索系统"按钮";
                                }
                            },
                            
                            // 获取单个索引器状态
                            getIndexerStatus(indexerId) {
                                const domainId = "jackett_" + indexerId.toLowerCase();
                                return this.systemIndexers.includes(domainId) ? "已添加" : "未添加";
                            }
                        }
                    }
                '''
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
            # 强制启用插件功能
            self._enabled = True
            
            # 先清理已有索引器
            self._remove_jackett_indexers()
            
            # 清空已添加索引器列表
            self._added_indexers = []
            
            # 重新加载
            self._add_jackett_indexers()
            
            # 获取Jackett索引器，确保所有数据最新
            jackett_indexers = self._fetch_jackett_indexers()
            all_indexers = []
            for indexer in jackett_indexers:
                formatted = self._format_indexer(indexer)
                if formatted:
                    all_indexers.append((formatted["id"], formatted))
            
            # 尝试通过多种方式写入系统配置
            write_success = False
            
            # 1. 尝试使用SystemConfigOper
            try:
                from app.db.systemconfig_oper import SystemConfigOper
                from app.schemas.types import SystemConfigKey
                
                # 获取当前索引器配置 - 兼容不同版本
                config_oper = SystemConfigOper()
                
                # 探测系统配置键
                config_keys = []
                try:
                    for attr in dir(SystemConfigKey):
                        if not attr.startswith('_'):
                            config_keys.append(attr)
                    print(f"【{self.plugin_name}】系统配置键: {config_keys}")
                except Exception as e:
                    print(f"【{self.plugin_name}】无法获取SystemConfigKey枚举: {str(e)}")
                
                # 尝试所有可能的系统配置键
                for key_name in ["UserIndexer", "INDEXER", "Indexer", "indexer"]:
                    try:
                        # 获取现有配置
                        if hasattr(SystemConfigKey, key_name):
                            key_obj = getattr(SystemConfigKey, key_name)
                            indexers_config = config_oper.get(key_obj) or {}
                        else:
                            indexers_config = config_oper.get(key_name) or {}
                        
                        # 清除已有的Jackett索引器
                        jackett_keys = [k for k in indexers_config.keys() if k.startswith("jackett_")]
                        for key in jackett_keys:
                            if key in indexers_config:
                                del indexers_config[key]
                        
                        # 添加新的Jackett索引器
                        for indexer_id, indexer_config in all_indexers:
                            indexers_config[indexer_id] = indexer_config
                        
                        # 保存配置
                        if hasattr(SystemConfigKey, key_name):
                            key_obj = getattr(SystemConfigKey, key_name)
                            config_oper.set(key_obj, indexers_config)
                        else:
                            config_oper.set(key_name, indexers_config)
                        
                        print(f"【{self.plugin_name}】成功使用配置键 '{key_name}' 写入 {len(all_indexers)} 个索引器")
                        write_success = True
                        break
                    except Exception as e:
                        print(f"【{self.plugin_name}】使用配置键 '{key_name}' 写入失败: {str(e)}")
            except Exception as e:
                print(f"【{self.plugin_name}】使用SystemConfigOper写入失败: {str(e)}")
                import traceback
                print(f"【{self.plugin_name}】异常详情: {traceback.format_exc()}")
            
            # 2. 尝试直接修改系统配置文件
            if not write_success:
                try:
                    import os
                    import yaml
                    
                    # 查找配置文件
                    config_paths = [
                        "/config/user.yaml",
                        "/config/config.yaml",
                        "/app/config/user.yaml",
                        "/app/config/config.yaml"
                    ]
                    
                    for config_path in config_paths:
                        if os.path.exists(config_path):
                            print(f"【{self.plugin_name}】找到配置文件: {config_path}")
                            
                            # 检查写权限
                            if not os.access(config_path, os.W_OK):
                                print(f"【{self.plugin_name}】配置文件无写权限: {config_path}")
                                continue
                                
                            # 备份文件
                            backup_path = f"{config_path}.bak.{int(time.time())}"
                            try:
                                with open(config_path, 'r', encoding='utf-8') as f:
                                    content = f.read()
                                with open(backup_path, 'w', encoding='utf-8') as f:
                                    f.write(content)
                                print(f"【{self.plugin_name}】已创建配置文件备份: {backup_path}")
                            except Exception as e:
                                print(f"【{self.plugin_name}】创建备份失败: {str(e)}")
                            
                            # 读取配置
                            try:
                                with open(config_path, 'r', encoding='utf-8') as f:
                                    config_data = yaml.safe_load(f) or {}
                            except Exception as e:
                                print(f"【{self.plugin_name}】读取配置文件失败: {str(e)}")
                                continue
                            
                            # 添加索引器
                            indexer_section = None
                            for section_name in ['indexer', 'INDEXER', 'Indexer', 'UserIndexer', 'user_indexer']:
                                if section_name in config_data:
                                    indexer_section = section_name
                                    break
                            
                            if not indexer_section:
                                # 没有找到索引器部分，创建一个
                                indexer_section = 'indexer'
                                config_data[indexer_section] = {}
                                print(f"【{self.plugin_name}】在配置中创建新的索引器部分: {indexer_section}")
                            
                            # 准备所有索引器
                            indexer_count = 0
                            for indexer in indexers:
                                formatted = self._format_indexer(indexer)
                                if formatted:
                                    indexer_id = formatted["id"]
                                    config_data[indexer_section][indexer_id] = formatted
                                    indexer_count += 1
                            
                            print(f"【{self.plugin_name}】添加了 {indexer_count} 个索引器到配置")
                            
                            # 保存配置
                            try:
                                # 使用yaml保存
                                with open(config_path, 'w', encoding='utf-8') as f:
                                    yaml.dump(config_data, f, allow_unicode=True)
                                print(f"【{self.plugin_name}】成功保存配置文件")
                                
                                # 修改文件时间戳，确保系统检测到变化
                                os.utime(config_path, None)
                                print(f"【{self.plugin_name}】已更新配置文件时间戳")
                                
                                # 尝试触发重启
                                self._try_restart_system()
                                
                                return True
                            except Exception as e:
                                print(f"【{self.plugin_name}】保存配置文件失败: {str(e)}")
                                
                            break
                except Exception as e:
                    print(f"【{self.plugin_name}】直接修改配置文件失败: {str(e)}")
                    import traceback
                    print(f"【{self.plugin_name}】异常详情: {traceback.format_exc()}")
            
            # 尝试触发系统重载 - 如果找不到其他更好的导入方法，尝试通过其他服务接口
            try:
                # 尝试寻找可用的重启方法
                restart_methods = [
                    ("app.app", "restart"),
                    ("app.core.config", "reload"),
                    ("app.core.module", "restart"),
                    ("app.utils.system", "reboot"),
                    ("app.core.context", "restart_service")
                ]
                
                for module_path, method_name in restart_methods:
                    try:
                        module = importlib.import_module(module_path)
                        if hasattr(module, method_name):
                            method = getattr(module, method_name)
                            if callable(method):
                                print(f"【{self.plugin_name}】找到系统重载方法: {module_path}.{method_name}")
                                method()
                                print(f"【{self.plugin_name}】已触发系统重启")
                                break
                    except (ImportError, AttributeError):
                        continue
                
                # 尝试通过触发文件系统变化来触发重载
                try:
                    import os
                    import time
                    
                    # 寻找配置目录
                    config_paths = [
                        "/config",
                        "/app/config",
                        "/config/user.yaml",
                        "/config/config.yaml"
                    ]
                    
                    for path in config_paths:
                        if os.path.exists(path):
                            # 如果是文件，更新其访问和修改时间
                            if os.path.isfile(path):
                                try:
                                    # 更新文件的访问和修改时间到当前时间
                                    os.utime(path, None)
                                    print(f"【{self.plugin_name}】已更新文件时间戳: {path}")
                                except Exception as e:
                                    print(f"【{self.plugin_name}】更新文件时间戳失败: {str(e)}")
                            
                            # 如果是目录，创建并删除临时文件来触发文件系统事件
                            elif os.path.isdir(path):
                                try:
                                    temp_file = os.path.join(path, f".jackett_reload_{int(time.time())}")
                                    with open(temp_file, 'w') as f:
                                        f.write(f"Jackett reload trigger {time.time()}")
                                    print(f"【{self.plugin_name}】已创建临时文件: {temp_file}")
                                    time.sleep(2)  # 等待文件系统事件传播
                                    if os.path.exists(temp_file):
                                        os.remove(temp_file)
                                        print(f"【{self.plugin_name}】已删除临时文件: {temp_file}")
                                except Exception as e:
                                    print(f"【{self.plugin_name}】创建/删除临时文件失败: {str(e)}")
                            
                            break
                except Exception as e:
                    print(f"【{self.plugin_name}】尝试通过文件系统触发重载失败: {str(e)}")
            except Exception as e:
                print(f"【{self.plugin_name}】触发系统重载失败: {str(e)}")
                import traceback
                print(f"【{self.plugin_name}】重载异常详情: {traceback.format_exc()}")
            
            # 返回成功消息
            if write_success:
                return {"code": 0, "message": f"重新加载索引器成功，共添加{len(all_indexers)}个索引器。系统可能需要重启才能生效。"}
            else:
                return {"code": 1, "message": "重新加载索引器失败，请检查日志。"}
                
        except Exception as e:
            print(f"【{self.plugin_name}】重新加载索引器异常: {str(e)}")
            import traceback
            print(f"【{self.plugin_name}】异常详情: {traceback.format_exc()}")
            return {"code": 1, "message": f"重新加载索引器失败: {str(e)}"}

    def get_indexers(self):
        """
        获取索引器列表
        """
        print(f"【{self.plugin_name}】正在获取索引器列表...")
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
            
            # 检查系统中已添加的索引器
            try:
                # 导入 SitesHelper
                sites_helper = None
                try:
                    # 尝试 V2 版本的导入路径
                    from app.helper.sites import SitesHelper
                    sites_helper = SitesHelper()
                except ImportError:
                    try:
                        # 尝试 V1 版本的导入路径
                        from app.sites import SitesHelper
                        sites_helper = SitesHelper()
                    except ImportError as e:
                        print(f"【{self.plugin_name}】导入SitesHelper失败: {str(e)}")
                        return {"code": 0, "data": formatted_indexers}
                
                if not sites_helper:
                    print(f"【{self.plugin_name}】无法创建SitesHelper实例")
                    return {"code": 0, "data": formatted_indexers}
                
                # 获取系统中的索引器
                all_sites = []
                if hasattr(sites_helper, "get_indexers"):
                    all_sites = sites_helper.get_indexers() or []
                elif hasattr(sites_helper, "get_all_indexers"):
                    all_sites = sites_helper.get_all_indexers() or []
                
                # 检查all_sites的类型并处理
                jackett_sites = []
                if isinstance(all_sites, dict):
                    jackett_sites = [s for s in all_sites.keys() if isinstance(s, str) and s.startswith("jackett_")]
                else:
                    jackett_sites = [s for s in all_sites if isinstance(s, str) and s.startswith("jackett_")]
                
                print(f"【{self.plugin_name}】系统中共有 {len(jackett_sites)} 个Jackett索引器: {jackett_sites}")
                print(f"【{self.plugin_name}】Jackett服务中共有 {len(formatted_indexers)} 个索引器")
                
                # 添加额外信息
                return {
                    "code": 0, 
                    "data": formatted_indexers,
                    "system_indexers": jackett_sites,
                    "indexer_count": len(jackett_sites)
                }
                
            except Exception as e:
                print(f"【{self.plugin_name}】获取系统索引器异常: {str(e)}")
                import traceback
                print(f"【{self.plugin_name}】异常详情: {traceback.format_exc()}")
                return {"code": 0, "data": formatted_indexers}
                
        except Exception as e:
            print(f"【{self.plugin_name}】获取索引器异常: {str(e)}")
            return {"code": 1, "message": f"获取索引器异常: {str(e)}"}

    def get_state(self) -> bool:
        """
        获取插件状态
        """
        # 确保返回明确的布尔值
        state = bool(self._enabled and self._host and self._api_key)
        print(f"【{self.plugin_name}】get_state返回: {state}, enabled={self._enabled}, host={bool(self._host)}, api_key={bool(self._api_key)}")
        return state

    def _remove_jackett_indexers(self):
        """
        从 MoviePilot 中移除 Jackett 索引器
        """
        try:
            # 导入 SitesHelper
            sites_helper = None
            try:
                # 尝试 V2 版本的导入路径
                from app.helper.sites import SitesHelper
                sites_helper = SitesHelper()
                print(f"【{self.plugin_name}】成功导入SitesHelper (V2路径)，准备移除索引器")
            except ImportError:
                try:
                    # 尝试 V1 版本的导入路径
                    from app.sites import SitesHelper
                    sites_helper = SitesHelper()
                    print(f"【{self.plugin_name}】成功导入SitesHelper (V1路径)，准备移除索引器")
                except ImportError as e:
                    print(f"【{self.plugin_name}】导入SitesHelper失败: {str(e)}")
                    return
            
            if not sites_helper:
                print(f"【{self.plugin_name}】无法创建SitesHelper实例")
                return

            # 移除已添加的索引器
            removed_count = 0
            
            # 检查SitesHelper是否有remove_indexer方法
            if hasattr(sites_helper, "remove_indexer"):
                for domain in self._added_indexers:
                    try:
                        sites_helper.remove_indexer(domain=domain)
                        removed_count += 1
                        print(f"【{self.plugin_name}】成功移除索引器: {domain}")
                    except Exception as e:
                        print(f"【{self.plugin_name}】移除索引器失败: {domain} - {str(e)}")
            else:
                # 尝试替代方法移除索引器
                try:
                    print(f"【{self.plugin_name}】SitesHelper没有remove_indexer方法，尝试使用替代方式移除")
                    # 检查其他可能的方法
                    if hasattr(sites_helper, "delete_indexer"):
                        for domain in self._added_indexers:
                            try:
                                sites_helper.delete_indexer(domain=domain)
                                removed_count += 1
                                print(f"【{self.plugin_name}】使用delete_indexer成功移除索引器: {domain}")
                            except Exception as e:
                                print(f"【{self.plugin_name}】使用delete_indexer移除索引器失败: {domain} - {str(e)}")
                    elif hasattr(sites_helper, "__remove_indexer"):
                        for domain in self._added_indexers:
                            try:
                                sites_helper.__remove_indexer(domain=domain)
                                removed_count += 1
                                print(f"【{self.plugin_name}】使用__remove_indexer成功移除索引器: {domain}")
                            except Exception as e:
                                print(f"【{self.plugin_name}】使用__remove_indexer移除索引器失败: {domain} - {str(e)}")
                    else:
                        print(f"【{self.plugin_name}】没有找到可用的移除索引器方法，将只清空内部列表")
                except Exception as e:
                    print(f"【{self.plugin_name}】尝试替代方式移除索引器异常: {str(e)}")
                    
            # 清空已添加索引器列表
            self._added_indexers = []
            print(f"【{self.plugin_name}】共移除了 {removed_count} 个索引器")
            
        except Exception as e:
            print(f"【{self.plugin_name}】移除Jackett索引器异常: {str(e)}")
            import traceback
            print(f"【{self.plugin_name}】异常详情: {traceback.format_exc()}")

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
            "id": "jackett_update_indexers",
            "name": "更新Jackett索引器",
            "trigger": "interval",
            "func": self._add_jackett_indexers,
            "kwargs": {"hours": 12}
        }]

    def _direct_register_indexers(self, indexers):
        """
        直接向MoviePilot核心注册索引器
        """
        print(f"【{self.plugin_name}】尝试直接修改核心应用中的索引器...")
        
        # 尝试找到并直接操作MoviePilot的索引器模块
        try:
            import importlib
            import os
            import json
            
            # 格式化所有需要的索引器
            formatted_indexers = {}
            for indexer in indexers:
                if self._indexers and indexer.get("id") not in self._indexers:
                    continue
                    
                formatted = self._format_indexer(indexer)
                if formatted:
                    indexer_id = formatted["id"]
                    formatted_indexers[indexer_id] = formatted
                    
            if not formatted_indexers:
                print(f"【{self.plugin_name}】没有有效的索引器可添加")
                return
                
            print(f"【{self.plugin_name}】准备添加 {len(formatted_indexers)} 个索引器")
            
            # 将索引器信息写入临时文件，方便核心应用读取
            temp_dir = "/tmp"
            if not os.path.exists(temp_dir):
                temp_dir = "."
                
            temp_file = os.path.join(temp_dir, f"jackett_indexers_{int(time.time())}.json")
            try:
                with open(temp_file, 'w', encoding='utf-8') as f:
                    json.dump(formatted_indexers, f, ensure_ascii=False)
                print(f"【{self.plugin_name}】已将索引器信息写入临时文件: {temp_file}")
            except Exception as e:
                print(f"【{self.plugin_name}】写入临时文件失败: {str(e)}")
                
            # 尝试找到配置文件路径
            config_dir = None
            for path in ["/config", "/app/config", "/data/config"]:
                if os.path.exists(path) and os.path.isdir(path):
                    config_dir = path
                    break
                    
            if not config_dir:
                print(f"【{self.plugin_name}】未找到配置目录")
                return
                
            # 创建一个触发文件通知系统重载索引器
            trigger_file = os.path.join(config_dir, ".load_jackett_indexers")
            try:
                with open(trigger_file, 'w', encoding='utf-8') as f:
                    f.write(temp_file)
                print(f"【{self.plugin_name}】已创建触发文件: {trigger_file}")
            except Exception as e:
                print(f"【{self.plugin_name}】创建触发文件失败: {str(e)}")
                
            # 修改触发文件的时间戳
            try:
                os.utime(trigger_file, None)
                print(f"【{self.plugin_name}】已更新触发文件时间戳")
            except Exception as e:
                print(f"【{self.plugin_name}】更新触发文件时间戳失败: {str(e)}")
            
            # 尝试导入并直接调用系统服务
            try:
                print(f"【{self.plugin_name}】尝试获取Movie Pilot运行模式...")
                try:
                    # 尝试获取系统运行模式
                    from app.utils.commons import RUNTIME_ENV
                    print(f"【{self.plugin_name}】系统运行模式: {RUNTIME_ENV}")
                except ImportError:
                    print(f"【{self.plugin_name}】无法获取系统运行模式")
                
                # 尝试直接创建数据库连接添加索引器
                try:
                    # 导入数据库操作类
                    print(f"【{self.plugin_name}】尝试通过数据库添加索引器...")
                    
                    # 尝试多种可能的导入路径
                    db_class = None
                    for module_path in [
                        "app.db.systemconfig_oper", 
                        "app.helper.db", 
                        "app.db",
                        "app.modules.database"
                    ]:
                        try:
                            module = importlib.import_module(module_path)
                            if hasattr(module, "SystemConfigOper"):
                                db_class = module.SystemConfigOper
                                print(f"【{self.plugin_name}】找到系统配置操作类: {module_path}.SystemConfigOper")
                                break
                        except ImportError:
                            continue
                    
                    if db_class:
                        # 创建实例
                        db_instance = db_class()
                        
                        # 尝试获取系统配置键
                        config_keys = []
                        try:
                            from app.schemas.types import SystemConfigKey
                            for attr in dir(SystemConfigKey):
                                if not attr.startswith('_'):
                                    config_keys.append(attr)
                            print(f"【{self.plugin_name}】系统配置键: {config_keys}")
                        except ImportError:
                            print(f"【{self.plugin_name}】无法导入SystemConfigKey")
                        
                        # 尝试通过数据库直接写入配置
                        for key_name in ["UserIndexer", "INDEXER", "Indexer", "indexer"]:
                            try:
                                # 获取现有配置
                                existing_config = {}
                                if hasattr(db_instance, "get") and callable(db_instance.get):
                                    try:
                                        from app.schemas.types import SystemConfigKey
                                        if hasattr(SystemConfigKey, key_name):
                                            key_obj = getattr(SystemConfigKey, key_name)
                                            existing_config = db_instance.get(key_obj) or {}
                                            print(f"【{self.plugin_name}】使用SystemConfigKey.{key_name}获取配置")
                                        else:
                                            existing_config = db_instance.get(key_name) or {}
                                            print(f"【{self.plugin_name}】使用字符串键'{key_name}'获取配置")
                                    except Exception as e:
                                        print(f"【{self.plugin_name}】获取配置失败: {str(e)}")
                                
                                # 添加新索引器
                                for indexer_id, indexer_data in formatted_indexers.items():
                                    existing_config[indexer_id] = indexer_data
                                
                                # 保存配置
                                if hasattr(db_instance, "set") and callable(db_instance.set):
                                    try:
                                        from app.schemas.types import SystemConfigKey
                                        if hasattr(SystemConfigKey, key_name):
                                            key_obj = getattr(SystemConfigKey, key_name)
                                            db_instance.set(key_obj, existing_config)
                                            print(f"【{self.plugin_name}】使用SystemConfigKey.{key_name}保存配置")
                                        else:
                                            db_instance.set(key_name, existing_config)
                                            print(f"【{self.plugin_name}】使用字符串键'{key_name}'保存配置")
                                        
                                        print(f"【{self.plugin_name}】成功保存索引器到数据库")
                                        break
                                    except Exception as e:
                                        print(f"【{self.plugin_name}】保存配置失败: {str(e)}")
                            except Exception as e:
                                print(f"【{self.plugin_name}】使用键'{key_name}'操作失败: {str(e)}")
                    else:
                        print(f"【{self.plugin_name}】未找到系统配置操作类")
                
                except Exception as e:
                    print(f"【{self.plugin_name}】通过数据库添加索引器失败: {str(e)}")
                    import traceback
                    print(f"【{self.plugin_name}】异常详情: {traceback.format_exc()}")
                
            except Exception as e:
                print(f"【{self.plugin_name}】尝试通过系统服务添加索引器失败: {str(e)}")
                import traceback
                print(f"【{self.plugin_name}】异常详情: {traceback.format_exc()}")
            
        except Exception as e:
            print(f"【{self.plugin_name}】尝试直接注册索引器失败: {str(e)}")
            import traceback
            print(f"【{self.plugin_name}】异常详情: {traceback.format_exc()}")
            
    def _direct_modify_config_file(self, indexers):
        """
        直接修改MoviePilot配置文件来添加索引器
        """
        print(f"【{self.plugin_name}】尝试直接修改系统配置文件...")
        try:
            import os
            import yaml
            import json
            import time
            
            # 查找配置文件
            config_paths = [
                "/config/user.yaml",
                "/config/config.yaml",
                "/app/config/user.yaml", 
                "/app/config/config.yaml"
            ]
            
            for config_path in config_paths:
                if os.path.exists(config_path):
                    print(f"【{self.plugin_name}】找到配置文件: {config_path}")
                    
                    # 检查写权限
                    if not os.access(config_path, os.W_OK):
                        print(f"【{self.plugin_name}】配置文件无写权限: {config_path}")
                        continue
                        
                    # 备份文件
                    backup_path = f"{config_path}.bak.{int(time.time())}"
                    try:
                        with open(config_path, 'r', encoding='utf-8') as f:
                            content = f.read()
                        with open(backup_path, 'w', encoding='utf-8') as f:
                            f.write(content)
                        print(f"【{self.plugin_name}】已创建配置文件备份: {backup_path}")
                    except Exception as e:
                        print(f"【{self.plugin_name}】创建备份失败: {str(e)}")
                    
                    # 读取配置
                    try:
                        with open(config_path, 'r', encoding='utf-8') as f:
                            config_data = yaml.safe_load(f) or {}
                    except Exception as e:
                        print(f"【{self.plugin_name}】读取配置文件失败: {str(e)}")
                        continue
                    
                    # 添加索引器
                    indexer_section = None
                    for section_name in ['indexer', 'INDEXER', 'Indexer', 'UserIndexer', 'user_indexer']:
                        if section_name in config_data:
                            indexer_section = section_name
                            break
                    
                    if not indexer_section:
                        # 没有找到索引器部分，创建一个
                        indexer_section = 'indexer'
                        config_data[indexer_section] = {}
                        print(f"【{self.plugin_name}】在配置中创建新的索引器部分: {indexer_section}")
                    
                    # 准备所有索引器
                    indexer_count = 0
                    for indexer in indexers:
                        formatted = self._format_indexer(indexer)
                        if formatted:
                            indexer_id = formatted["id"]
                            config_data[indexer_section][indexer_id] = formatted
                            indexer_count += 1
                    
                    print(f"【{self.plugin_name}】添加了 {indexer_count} 个索引器到配置")
                    
                    # 保存配置
                    try:
                        # 使用yaml保存
                        with open(config_path, 'w', encoding='utf-8') as f:
                            yaml.dump(config_data, f, allow_unicode=True)
                        print(f"【{self.plugin_name}】成功保存配置文件")
                        
                        # 修改文件时间戳，确保系统检测到变化
                        os.utime(config_path, None)
                        print(f"【{self.plugin_name}】已更新配置文件时间戳")
                        
                        # 尝试触发重启
                        self._try_restart_system()
                        
                        return True
                    except Exception as e:
                        print(f"【{self.plugin_name}】保存配置文件失败: {str(e)}")
                        
            print(f"【{self.plugin_name}】未找到可写的配置文件")
            return False
            
        except Exception as e:
            print(f"【{self.plugin_name}】直接修改配置文件异常: {str(e)}")
            import traceback
            print(f"【{self.plugin_name}】异常详情: {traceback.format_exc()}")
            return False
    
    def _try_restart_system(self):
        """
        尝试重启系统
        """
        print(f"【{self.plugin_name}】尝试重启系统以刷新索引器...")
        try:
            import sys
            import signal
            import os
            
            # 尝试导入系统重启方法
            try:
                import importlib
                for module_path in [
                    'app.utils.system',
                    'app.core.system',
                    'app.app',
                    'app',
                    'main'
                ]:
                    try:
                        module = importlib.import_module(module_path)
                        for method_name in ['restart', 'reboot', 'reload']:
                            if hasattr(module, method_name):
                                restart_method = getattr(module, method_name)
                                if callable(restart_method):
                                    print(f"【{self.plugin_name}】找到系统重启方法: {module_path}.{method_name}")
                                    restart_method()
                                    print(f"【{self.plugin_name}】已触发系统重启")
                                    return True
                    except (ImportError, AttributeError):
                        continue
            except Exception as e:
                print(f"【{self.plugin_name}】尝试导入重启方法失败: {str(e)}")
            
            # 尝试通过进程信号重启
            print(f"【{self.plugin_name}】尝试通过进程信号重启系统...")
            try:
                # 检查是否在容器内
                if os.path.exists('/.dockerenv'):
                    # 尝试发送SIGHUP信号通知系统重载
                    os.kill(1, signal.SIGHUP)
                    print(f"【{self.plugin_name}】已发送SIGHUP信号到PID 1")
                else:
                    # 尝试发送重载信号到当前进程
                    os.kill(os.getpid(), signal.SIGHUP)
                    print(f"【{self.plugin_name}】已发送SIGHUP信号到当前进程")
                return True
            except Exception as e:
                print(f"【{self.plugin_name}】通过进程信号重启失败: {str(e)}")
            
            return False
        except Exception as e:
            print(f"【{self.plugin_name}】尝试重启系统异常: {str(e)}")
            return False 