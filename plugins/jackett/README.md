# Jackett 插件

这是一个用于 MoviePilot 的 Jackett 搜索插件，可以将 Jackett 索引器的搜索结果整合到 MoviePilot 的资源搜索中。

## 功能特性

- 支持配置 Jackett 服务器地址和 API Key
- 支持选择性启用特定的索引器
- 通过事件机制，将 Jackett 搜索结果整合到 MoviePilot 的资源搜索中

## 工作原理

Jackett 插件通过监听 MoviePilot 的搜索事件（`EventType.SearchTorrent`），在搜索发生时调用 Jackett API 进行资源检索，并将结果返回给 MoviePilot 的搜索系统。插件使用事件响应方式工作，不会影响 MoviePilot 原有的搜索过程。

## 配置说明

1. 启用插件：开启或关闭插件功能
2. Jackett地址：填写 Jackett 服务器的访问地址，例如：http://localhost:9117
3. API Key：填写 Jackett 的 API Key，可在 Jackett 管理界面右上角找到
4. 管理密码：如果 Jackett 设置了管理密码，需要填写，否则留空
5. 索引器：选择要启用的索引器（可多选）

## 使用方法

1. 确保 Jackett 服务器正常运行，并已配置好索引器
2. 在 MoviePilot 插件市场中添加此仓库地址
3. 安装并启用 Jackett 插件
4. 配置插件参数并保存
5. MoviePilot 进行资源搜索时，会自动调用 Jackett 进行检索

## 搜索过程

1. MoviePilot 发起搜索请求
2. Jackett 插件接收到搜索事件
3. 插件调用 Jackett API 获取索引器列表
4. 根据配置，选择特定的索引器进行搜索
5. 获取搜索结果并解析
6. 将结果整合到 MoviePilot 的搜索结果中

## 注意事项

1. 请确保 MoviePilot 服务器可以访问 Jackett 服务
2. API Key 请妥善保管，不要泄露
3. 建议选择合适的索引器以提高搜索效率
4. 如果 Jackett 配置了管理密码，插件会自动处理登录认证

## API 接口

### 获取索引器列表

- 接口地址：`/api/v1/jackett/indexers`
- 请求方式：GET
- 返回格式：
  ```json
  {
    "code": 0,
    "data": [
      {
        "id": "索引器ID",
        "name": "索引器名称",
        ...
      }
    ]
  }
  ``` 