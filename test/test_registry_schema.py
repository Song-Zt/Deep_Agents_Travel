
import inspect

from tools.registry import (
    TOOL_REGISTRY,
    get_tool_schemas,
    get_tool_parameters_schema,
    python_type_to_json_schema,
)


def test_all_tools_have_schemas():
    """所有注册工具都应该生成 Schema。"""

    schemas = get_tool_schemas()

    assert len(schemas) == 9

    schema_names = {
        item["function"]["name"]
        for item in schemas
    }

    assert schema_names == set(TOOL_REGISTRY.keys())


def test_schema_has_function_calling_structure():
    """检查 Function Calling 格式。"""

    schemas = get_tool_schemas()

    for item in schemas:
        assert item["type"] == "function"

        function = item["function"]

        assert function["name"]
        assert function["description"]

        parameters = function["parameters"]

        assert parameters["type"] == "object"
        assert "properties" in parameters


def test_weather_schema():
    """检查天气工具的参数 Schema。"""

    schemas = get_tool_schemas()

    weather_schema = next(
        item["function"]
        for item in schemas
        if item["function"]["name"] == "get_weather"
    )

    parameters = weather_schema["parameters"]

    assert "city" in parameters["properties"]
    assert parameters["properties"]["city"]["type"] == "string"
    assert "city" in parameters["required"]


def test_required_parameters_follow_function_signature():
    """Schema 的必填参数应与函数签名一致。"""

    for tool_name, tool in TOOL_REGISTRY.items():

        schema = get_tool_parameters_schema(tool)

        expected_required = [
            name
            for name, parameter in inspect.signature(tool).parameters.items()
            if parameter.default is inspect.Parameter.empty
            and parameter.kind not in (
                inspect.Parameter.VAR_POSITIONAL,
                inspect.Parameter.VAR_KEYWORD,
            )
        ]

        assert set(schema.get("required", [])) == set(
            expected_required
        )


def test_python_type_conversion():
    """测试 Python 类型转换。"""

    assert python_type_to_json_schema(str) == {
        "type": "string"
    }

    assert python_type_to_json_schema(int) == {
        "type": "integer"
    }

    assert python_type_to_json_schema(float) == {
        "type": "number"
    }

    assert python_type_to_json_schema(bool) == {
        "type": "boolean"
    }


def test_list_type_conversion():
    """测试列表类型转换。"""

    result = python_type_to_json_schema(list[str])

    assert result == {
        "type": "array",
        "items": {
            "type": "string"
        }
    }
