# MoviePilot 插件

这是一个 MoviePilot 的第三方插件仓库，提供以下插件：

## 插件列表

### Jackett
- 版本：1.0
- 描述：支持 Jackett 搜索器，用于资源检索
- 作者：lightolly
- 用户等级：2（认证用户可见）

## 使用说明

### Jackett 插件

#### 功能特性

- 支持配置 Jackett 服务器地址和 API Key
- 支持选择性启用特定的索引器
- 通过事件机制，将 Jackett 搜索结果整合到 MoviePilot 的资源搜索中

#### 配置方法

1. 启用插件：开启或关闭插件功能
2. Jackett地址：填写 Jackett 服务器的访问地址，例如：http://localhost:9117
3. API Key：填写 Jackett 的 API Key，可在 Jackett 管理界面右上角找到
4. 管理密码：如果 Jackett 设置了管理密码，需要填写，否则留空
5. 索引器：选择要启用的索引器（可多选）

#### 使用方法

1. 确保 Jackett 服务器正常运行，并已配置好索引器
2. 在 MoviePilot 插件市场中添加此仓库地址
3. 安装并启用 Jackett 插件
4. 配置插件参数并保存
5. MoviePilot 进行资源搜索时，会自动调用 Jackett 进行检索

#### 注意事项

1. 请确保 MoviePilot 服务器可以访问 Jackett 服务
2. API Key 请妥善保管，不要泄露
3. 建议选择合适的索引器以提高搜索效率

## 目录结构

```
├── plugins/              # 插件目录
│   └── jackett/         # Jackett插件
│       ├── __init__.py
│       ├── requirements.txt
│       └── README.md
├── package.json         # 插件配置
└── README.md           # 项目说明
```

## 开发说明

本仓库遵循 MoviePilot 官方的插件开发规范，详情请参考：
- [MoviePilot 插件开发文档](https://github.com/jxxghp/MoviePilot-Plugins)
- [MoviePilot V2 插件开发指南](https://github.com/jxxghp/MoviePilot-Plugins/blob/main/docs/V2_Plugin_Development.md)

## 注意事项

1. 插件开发请遵循 MoviePilot 的开发规范
2. 确保插件版本号在 package.json/package.v2.json 和插件代码中保持一致
3. 插件更新时请同时更新版本号和更新说明 