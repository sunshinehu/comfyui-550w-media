import unittest
from unittest.mock import patch
from adapter import Client, AdapterError, rectangle, share_url

class ContractTests(unittest.TestCase):
    def test_paid_actions_require_confirmation(self):
        client = Client('test-key', 'test-user')
        with patch.object(client, 'request') as request:
            for action in ('image', 'video', 'share'):
                with self.assertRaises(AdapterError):
                    client.execute(action)
            request.assert_not_called()

    def test_share_extracts_link_and_preserves_id(self):
        client = Client('test-key', 'test-user')
        with patch.object(client, 'request', return_value={'code': 200}) as request:
            client.execute('share', share_text='Share https://example.com/video', operation_id='same-id-123', confirm_charge=True)
            self.assertEqual(request.call_args.args[1]['operationId'], 'same-id-123')

    def test_full_frame_omits_rectangle(self):
        client = Client('test-key', 'test-user')
        uploaded = {'code': 200, 'videoUrl': 'https://example.com/video.mp4', 'width': 1280, 'height': 720, 'duration': 5}
        with patch.object(client, 'request', side_effect=[uploaded, {'code': 200}]) as request:
            client.execute('video', file_path='selected.mp4', idempotency_key='stable-key-123', confirm_charge=True)
            self.assertNotIn('x1', request.call_args.args[1])

    def test_invalid_rectangles_and_urls(self):
        for value in ([0, 0, 1.5, 3], [1, 0, 0, 3], [False, 0, 3, 3]):
            with self.assertRaises(AdapterError):
                rectangle(value)
        with self.assertRaises(AdapterError):
            share_url('https://user:password@example.com/file')

if __name__ == '__main__':
    unittest.main()
