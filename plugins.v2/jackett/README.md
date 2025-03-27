# Jackett 插件

这是一个用于 MoviePilot 的 Jackett 搜索插件，支持通过 Jackett 搜索资源。

## 功能特性

- 支持配置 Jackett 服务器地址和 API Key
- 支持选择性启用特定的索引器
- 支持资源搜索并返回结果
- 支持获取索引器列表

## 配置说明

1. 启用插件：开启或关闭插件功能
2. Jackett地址：填写 Jackett 服务器的访问地址，例如：http://localhost:9117
3. API Key：填写 Jackett 的 API Key
4. 索引器：选择要启用的索引器（可多选）

## 使用方法

1. 在插件配置页面填写相关配置信息
2. 启用插件后，系统会自动调用 Jackett 进行资源搜索
3. 可以通过 API 接口获取已配置的索引器列表

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

## 注意事项

1. 请确保 Jackett 服务器可以正常访问
2. API Key 请妥善保管，不要泄露
3. 建议选择合适的索引器以提高搜索效率 