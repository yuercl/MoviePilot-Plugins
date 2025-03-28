from typing import Dict, Any, List, Optional, Tuple
from app.plugins import _PluginBase
from app.utils.http import RequestUtils
import json
import os
import time
import xml.dom.minidom
from urllib.parse import urljoin
import requests

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
    plugin_version = "1.50"
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
            
            # 添加分类支持，使索引器支持影视搜索
            # 使用通用的Torznab分类
            category_config = {
                "movie": [
                    {"id": "2000", "desc": "Movies"},  # 电影主分类
                    {"id": "2010", "desc": "Movies/Foreign"},
                    {"id": "2020", "desc": "Movies/BluRay"},
                    {"id": "2030", "desc": "Movies/DVD"},
                    {"id": "2040", "desc": "Movies/HD"},
                    {"id": "2045", "desc": "Movies/UHD"},
                    {"id": "2050", "desc": "Movies/3D"},
                    {"id": "2060", "desc": "Movies/SD"}
                ],
                "tv": [
                    {"id": "5000", "desc": "TV"},  # 电视剧主分类
                    {"id": "5020", "desc": "TV/Blu-ray"},
                    {"id": "5030", "desc": "TV/DVD"},
                    {"id": "5040", "desc": "TV/HD"},
                    {"id": "5050", "desc": "TV/SD"},
                    {"id": "5060", "desc": "TV/Foreign"},
                    {"id": "5070", "desc": "TV/Sport"},
                    {"id": "5080", "desc": "TV/Anime"}
                ]
            }
            
            # 使用MoviePilot支持的格式
            mp_indexer = {
                "id": f"jackett_{indexer_id.lower()}",
                "name": f"[Jackett] {indexer_name}",
                "domain": self._host,
                "url": self._host,
                "encoding": "UTF-8",
                "public": True,
                "proxy": True,
                "language": "zh_CN",  # 添加默认语言
                "category": category_config,  # 添加分类
                "builtin": False,  # 非内置
                "result_type": "json",  # 结果类型
                "parse": "xml",  # 解析类型
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
                        "cat": "{cat}",  # 添加分类参数
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
                        "grabs": {
                            "selector": "torznab|attr[name=grabs]",
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
            
            # 尝试直接写入系统配置
            try:
                from app.db.systemconfig_oper import SystemConfigOper
                from app.schemas.types import SystemConfigKey
                
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
                
                # 直接获取所有已格式化的索引器
                all_indexers = []
                jackett_indexers = self._fetch_jackett_indexers()
                for indexer in jackett_indexers:
                    formatted = self._format_indexer(indexer)
                    if formatted:
                        all_indexers.append((formatted["id"], formatted))
                
                # 清除已有的Jackett索引器
                jackett_keys = [k for k in indexers_config.keys() if k.startswith("jackett_")]
                for key in jackett_keys:
                    if key in indexers_config:
                        del indexers_config[key]
                
                # 添加所有新格式化的Jackett索引器
                for indexer_id, indexer_config in all_indexers:
                    indexers_config[indexer_id] = indexer_config
                
                # 保存配置
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
                    print(f"【{self.plugin_name}】成功直接写入 {len(all_indexers)} 个索引器到系统配置")
                else:
                    print(f"【{self.plugin_name}】尝试了所有可能的配置键，仍无法保存索引器配置")
                
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
                    
                    print(f"【{self.plugin_name}】尝试发送模块重载事件...")
                    event_manager = EventManager()
                    event_manager.send_event(EventType.ModuleReload)
                    print(f"【{self.plugin_name}】成功发送模块重载事件")
                    
                    # 尝试发送站点刷新事件
                    event_manager.send_event(EventType.SiteRefreshed)
                    print(f"【{self.plugin_name}】成功发送站点刷新事件")
                except Exception as e:
                    print(f"【{self.plugin_name}】发送刷新事件失败: {str(e)}")
                
                return {"code": 0, "message": f"重新加载索引器成功，共添加{len(all_indexers)}个索引器"}
                
            except Exception as e:
                print(f"【{self.plugin_name}】直接写入系统配置失败: {str(e)}")
                import traceback
                print(f"【{self.plugin_name}】异常详情: {traceback.format_exc()}")
            
            # 如果直接写入失败，回退到检查添加结果
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
                        return {"code": 0, "message": f"重新加载索引器成功，共添加{len(self._added_indexers)}个索引器，但无法验证状态"}
                
                if not sites_helper:
                    print(f"【{self.plugin_name}】无法创建SitesHelper实例")
                    return {"code": 0, "message": f"重新加载索引器成功，共添加{len(self._added_indexers)}个索引器，但无法验证状态"}
                
                # 获取系统中的索引器
                all_sites = []
                if hasattr(sites_helper, "get_indexers"):
                    all_sites = sites_helper.get_indexers() or []
                elif hasattr(sites_helper, "get_all_indexers"):
                    all_sites = sites_helper.get_all_indexers() or []
                
                # 检查Jackett索引器是否在列表中
                jackett_sites = []
                if isinstance(all_sites, dict):
                    jackett_sites = [s for s in all_sites.keys() if isinstance(s, str) and s.startswith("jackett_")]
                else:
                    jackett_sites = [s for s in all_sites if isinstance(s, str) and s.startswith("jackett_")]
                
                if jackett_sites:
                    print(f"【{self.plugin_name}】成功添加 {len(jackett_sites)} 个Jackett索引器: {jackett_sites}")
                    return {"code": 0, "message": f"重新加载索引器成功，共添加{len(jackett_sites)}个索引器"}
                else:
                    print(f"【{self.plugin_name}】系统中未检测到Jackett索引器，可能添加失败")
                    return {"code": 1, "message": "索引器添加失败，请检查日志"}
            except Exception as e:
                print(f"【{self.plugin_name}】检查索引器状态异常: {str(e)}")
                import traceback
                print(f"【{self.plugin_name}】异常详情: {traceback.format_exc()}")
                return {"code": 0, "message": f"重新加载索引器成功，共添加{len(self._added_indexers)}个索引器，但无法验证状态"}
                
        except Exception as e:
            print(f"【{self.plugin_name}】重新加载索引器异常: {str(e)}")
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