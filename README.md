# MoviePilot 插件

这是一个 MoviePilot 的第三方插件仓库，提供以下插件：

## 插件列表

### Jackett
- 版本：1.0
- 描述：支持 Jackett 搜索器，用于资源检索
- 作者：lightolly
- 用户等级：2（认证用户可见）

## 目录结构

```
├── plugins/              # V1版本插件目录
│   └── jackett/         # Jackett插件
│       ├── __init__.py
│       ├── requirements.txt
│       └── README.md
├── plugins.v2/          # V2版本插件目录
│   └── jackett/        # Jackett插件
│       ├── __init__.py
│       ├── requirements.txt
│       └── README.md
├── package.json         # V1版本插件配置
├── package.v2.json      # V2版本插件配置
└── README.md           # 项目说明
```

## 使用说明

1. 在 MoviePilot 的插件市场中添加此仓库地址
2. 在插件市场中安装所需的插件
3. 根据插件说明进行配置和使用

## 开发说明

本仓库遵循 MoviePilot 官方的插件开发规范，详情请参考：
- [MoviePilot 插件开发文档](https://github.com/jxxghp/MoviePilot-Plugins)
- [MoviePilot V2 插件开发指南](https://github.com/jxxghp/MoviePilot-Plugins/blob/main/docs/V2_Plugin_Development.md)

## 注意事项

1. 插件开发请遵循 MoviePilot 的开发规范
2. 确保插件版本号在 package.json/package.v2.json 和插件代码中保持一致
3. 插件更新时请同时更新版本号和更新说明 