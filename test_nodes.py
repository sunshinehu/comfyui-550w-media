import unittest
import sys
import importlib.util
from pathlib import Path
from unittest.mock import patch
from types import SimpleNamespace

root = Path(__file__).parent
spec = importlib.util.spec_from_file_location("fiftyw_test_comfy",root / "__init__.py",submodule_search_locations=[str(root)])
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)
from fiftyw_test_comfy.tensor import ImageTensor
from fiftyw_test_comfy.results import completed_image_url, ImageResult

class NodeTest(unittest.TestCase):
    def test_result_redirect_rejected_without_credentials(self):
        import json
        from unittest.mock import MagicMock
        response = MagicMock()
        response.__enter__.return_value = response
        response.status_code = 302
        result = json.dumps({"code": 200, "status": "success", "resultUrl": "https://i.550wai.cn/image.jpg"})
        with patch("fiftyw_test_comfy.results.requests.get", return_value=response) as request:
            with self.assertRaises(ValueError):
                ImageResult().run(result)
        self.assertFalse(request.call_args.kwargs["allow_redirects"])
        self.assertNotIn("headers", request.call_args.kwargs)
        response.iter_content.assert_not_called()

    def test_result_native_image_and_host_guards(self):
        import json
        self.assertEqual(ImageResult.RETURN_TYPES, ("IMAGE",))
        valid = {"code": 200, "status": "success", "resultUrl": "https://i.550wai.cn/image.jpg"}
        self.assertEqual(completed_image_url(json.dumps(valid)), valid["resultUrl"])
        for url in ("http://i.550wai.cn/image.jpg", "https://i.550wai.cn.evil.test/a", "https://localhost/a", "https://user:secret@i.550wai.cn/a"):
            with self.assertRaises(ValueError):
                completed_image_url(json.dumps({**valid, "resultUrl": url}))
        with self.assertRaises(ValueError):
            completed_image_url(json.dumps({**valid, "status": "waiting"}))

    def test_native_node_registered(self):
        self.assertEqual(module.NODE_CLASS_MAPPINGS["FiftyWImageTensor"].RETURN_TYPES,("STRING",))
        self.assertIn("image",ImageTensor.INPUT_TYPES()["required"])

    def test_confirmation_required_before_tensor_access(self):
        with self.assertRaises(ValueError):
            ImageTensor().run(None,"stable-operation",False,"en")

    def test_batch_rejected_before_upload(self):
        with self.assertRaises(ValueError):
            ImageTensor().run(SimpleNamespace(shape=(2,100,100,3)),"stable-operation",True,"en")

    def test_native_tensor_upload_and_temporary_cleanup(self):
        import numpy as np
        class Tensor:
            shape = (1,10,10,3)
            def __getitem__(self, index): return self
            def detach(self): return self
            def cpu(self): return self
            def numpy(self): return np.zeros((10,10,3))
        paths = []
        def execute(self,action,**kwargs):
            path = Path(kwargs["file_path"])
            paths.append(path)
            self_test.assertTrue(path.is_file())
            self_test.assertEqual(action,"image")
            return {"code":200,"data":{"taskId":"task-123"}}
        self_test = self
        with patch.dict("os.environ",{"FIFTYW_API_KEY":"test-key","FIFTYW_USER_NO":"test-user"}), patch("fiftyw_test_comfy.tensor.Client.execute",execute):
            result = ImageTensor().run(Tensor(),"stable-operation",True,"en")
            self.assertIn("task-123",result[0])
        self.assertFalse(paths[0].exists())

if __name__ == "__main__": unittest.main()
