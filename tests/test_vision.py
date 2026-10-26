import base64
import asyncio
import os
import hashlib
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch, AsyncMock

from app.ai_agent import load_model_configs, run_agent
from app.ai_agent import ModelConfig
from app.vision import validate_image_data_url
from app import chat_images
from app import investment_memory as memory


class VisionInputTests(unittest.TestCase):
    def test_image_validation(self):
        png = b"\x89PNG\r\n\x1a\n" + b"content"
        data_url = "data:image/png;base64," + base64.b64encode(png).decode()
        self.assertEqual(validate_image_data_url(data_url), data_url)
        with self.assertRaises(ValueError):
            validate_image_data_url("data:image/png;base64," + base64.b64encode(b"not an image").decode())
        with self.assertRaises(ValueError):
            validate_image_data_url("data:image/png;base64,%%%%")

    def test_model_capability_is_endpoint_specific_and_overridable(self):
        config = ('[{"provider":"openai","model":"deepseek-flash","base_url":"https://api.deepseek.com",'
                  '"api_key_env":"TEST_MODEL_KEY"},'
                  '{"provider":"openai","model":"deepseek-flash","base_url":"https://example.com/v1",'
                  '"api_key_env":"TEST_MODEL_KEY"},'
                  '{"provider":"openai","model":"custom-vision","base_url":"https://example.com/v1",'
                  '"api_key_env":"TEST_MODEL_KEY","supports_vision":true}]')
        with patch.dict(os.environ, {"MODEL_CONFIG_JSON": config, "TEST_MODEL_KEY": "test", "PRIMARY_MODEL": ""}):
            models, error = load_model_configs()
        self.assertIsNone(error)
        self.assertEqual([item.supports_vision for item in models], [True, False, True])

    def test_non_vision_model_rejects_image_before_persistence(self):
        from fastapi import HTTPException
        from app.main import AIResearchRequest, ai_research

        config = ModelConfig("openai", "text-only", "https://example.com/v1", "test")
        with patch("app.main.load_model_configs", return_value=([config], None)):
            with self.assertRaises(HTTPException) as raised:
                asyncio.run(ai_research(
                    AIResearchRequest(question="图片是什么", image_data_url="data:image/png;base64,AA=="),
                    SimpleNamespace(state=SimpleNamespace(session={"reauth_at": 0})),
                ))
        self.assertEqual(raised.exception.status_code, 422)
        self.assertIn("不支持图片", raised.exception.detail)

    def test_chat_image_records_metadata_and_reuses_analysis(self):
        raw = b"\x89PNG\r\n\x1a\n" + b"\0" * 8 + (320).to_bytes(4, "big") + (180).to_bytes(4, "big") + b"pixels"
        image = "data:image/png;base64," + base64.b64encode(raw).decode()
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {"DATA_DIR": directory, "CONTAINER_RUNTIME": "false"}):
            with patch.dict(os.environ, {"MYSQL_PASSWORD": "", "MYSQL_PASSWORD_FILE": ""}):
                chat_images.initialize()
                saved = chat_images.save("owner-a", "session-a", "gold.png", image)
                self.assertEqual(saved["sha256"], hashlib.sha256(raw).hexdigest())
                self.assertEqual((saved["width"], saved["height"]), (320, 180))
                self.assertEqual(saved["byte_size"], len(raw))
                self.assertEqual(chat_images.save("owner-a", "session-a", "again.png", image)["image_id"], saved["image_id"])
                chat_images.set_content("owner-a", saved["image_id"], "黄金基金 35686.30 份")
                self.assertIn("35686.30", chat_images.context("owner-a", "session-a"))
                self.assertEqual(chat_images.data_url(chat_images.get("owner-a", saved["image_id"])), image)
                from fastapi import HTTPException
                with self.assertRaises(HTTPException):
                    chat_images.get("owner-b", saved["image_id"])

    def test_followup_uses_saved_image_analysis_without_market_evidence(self):
        config = ModelConfig("openai", "text-only", "https://example.com/v1", "test")
        async def no_tool(_name, _args):
            raise AssertionError("图片追问不应调用工具")
        with patch("app.ai_agent.load_model_configs", return_value=([config], None)), \
             patch("app.ai_agent._chat", new=AsyncMock(return_value={"content": "截图显示黄金基金 35668.30 份。"})):
            result = asyncio.run(run_agent("上面图片有多少份？\n同一会话已解析图片：黄金基金 35668.30 份", no_tool,
                                           tool_definitions=[], image_context_available=True))
        self.assertEqual(result["answer"], "截图显示黄金基金 35668.30 份。")

    def test_paste_endpoint_analyzes_before_a_text_prompt(self):
        from app.main import ChatImageInput, api_upload_chat_image
        raw = b"\x89PNG\r\n\x1a\n" + b"\0" * 24
        image = "data:image/png;base64," + base64.b64encode(raw).decode()
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {"DATA_DIR": directory, "CONTAINER_RUNTIME": "false", "MYSQL_PASSWORD": "", "MYSQL_PASSWORD_FILE": ""}):
            memory.initialize()
            with patch("app.main.security.current_owner_id", return_value="owner-a"), \
                 patch("app.main.load_model_configs", return_value=([SimpleNamespace(supports_vision=True)], None)), \
                 patch("app.main._chat", new=AsyncMock(return_value={"content": "可见黄金基金持仓，份额需要核对。"})) as model:
                result = asyncio.run(api_upload_chat_image(ChatImageInput(image_data_url=image, filename="黄金截图.png")))
            self.assertEqual(model.await_count, 1)
            self.assertEqual(result["filename"], "黄金截图.png")
            self.assertIn("份额需要核对", result["content"])
            self.assertEqual(chat_images.latest("owner-a", result["session_id"])["image_id"], result["image_id"])
            self.assertIn(result["sha256"], chat_images.context("owner-a", result["session_id"]))


if __name__ == "__main__":
    unittest.main()
