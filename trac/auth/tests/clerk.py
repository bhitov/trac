# -*- coding: utf-8 -*-

import unittest
from unittest.mock import Mock, patch, MagicMock
import urllib.parse
from http.cookies import SimpleCookie

from trac.test import EnvironmentStub, MockRequest
from trac.web.api import RequestDone
from trac.core import TracError

from trac.auth.clerk import ClerkConfig, ClerkAuthenticator, ClerkLoginModule


class ClerkConfigTestCase(unittest.TestCase):
    
    def setUp(self):
        self.env = EnvironmentStub()
        
    def test_env_vars_take_precedence_over_config(self):
        """Test that environment variables override trac.ini settings"""
        self.env.config.set('clerk', 'secret_key', 'config_key')
        
        with patch.dict('os.environ', {'CLERK_SECRET_KEY': 'env_key'}):
            config = ClerkConfig(self.env)
            self.assertEqual(config.secret_key(), 'env_key')
            
    def test_config_fallback_when_no_env_var(self):
        """Test that trac.ini is used when env var is not set"""
        self.env.config.set('clerk', 'secret_key', 'config_key')
        
        with patch.dict('os.environ', {}, clear=True):
            config = ClerkConfig(self.env)
            self.assertEqual(config.secret_key(), 'config_key')
            
    def test_default_values(self):
        """Test that default values are used when nothing is configured"""
        config = ClerkConfig(self.env)
        self.assertEqual(config.callback_path(), '/clerk/callback')
        self.assertEqual(config.after_sign_in_url(), '/')
        self.assertEqual(config.token_cookie_name(), 'clerk_session')
        # Default is 'true' string which evaluates to True
        with patch.dict('os.environ', {'CLERK_COOKIE_SECURE': 'true'}):
            self.assertTrue(ClerkConfig(self.env).cookie_secure())
        self.assertTrue(config.cookie_httponly())
        self.assertEqual(config.cookie_samesite(), 'Lax')
        
    def test_boolean_parsing(self):
        """Test that boolean values are parsed correctly"""
        self.env.config.set('clerk', 'cookie_secure', 'false')
        self.env.config.set('clerk', 'debug', 'true')
        
        config = ClerkConfig(self.env)
        self.assertFalse(config.cookie_secure())
        self.assertTrue(config.debug())


class ClerkAuthenticatorTestCase(unittest.TestCase):
    
    def setUp(self):
        self.env = EnvironmentStub(enable=[ClerkAuthenticator])
        self.env.config.set('clerk', 'secret_key', 'test_secret')
        self.authenticator = ClerkAuthenticator(self.env)
        
    def test_missing_secret_key_logs_and_denies_auth(self):
        """Test that missing secret key is handled gracefully"""
        self.env.config.remove('clerk', 'secret_key')
        req = MockRequest(self.env)
        
        result = self.authenticator.authenticate(req)
        self.assertIsNone(result)
        
    def test_authenticator_no_token_returns_none(self):
        """Test that missing token returns None"""
        req = MockRequest(self.env)
        
        with patch.object(self.authenticator, '_ensure_sdk') as mock_sdk:
            mock_clerk = Mock()
            mock_sdk.return_value = mock_clerk
            
            result = self.authenticator.authenticate(req)
            self.assertIsNone(result)
            
    @patch('trac.auth.clerk.Clerk')
    def test_authenticator_valid_cookie_returns_user_id(self, mock_clerk_class):
        """Test that valid token returns user ID"""
        req = MockRequest(self.env)
        req.incookie['clerk_session'] = 'valid_token'
        
        mock_clerk = Mock()
        mock_clerk_class.return_value = mock_clerk
        
        mock_session = Mock()
        mock_session.user_id = 'user_123'
        mock_clerk.sessions.verify_session.return_value = mock_session
        
        result = self.authenticator.authenticate(req)
        self.assertEqual(result, 'user_123')
        mock_clerk.sessions.verify_session.assert_called_once_with(session_id='valid_token')
        
    @patch('trac.auth.clerk.Clerk')  
    def test_authenticator_invalid_cookie_returns_none(self, mock_clerk_class):
        """Test that invalid token returns None"""
        req = MockRequest(self.env)
        req.incookie['clerk_session'] = 'invalid_token'
        
        mock_clerk = Mock()
        mock_clerk_class.return_value = mock_clerk
        
        from clerk_backend_api import SDKError
        mock_clerk.sessions.verify_session.side_effect = SDKError('Invalid token')
        
        result = self.authenticator.authenticate(req)
        self.assertIsNone(result)
        
    def test_extract_token_from_cookie(self):
        """Test token extraction from cookie"""
        req = MockRequest(self.env)
        req.incookie['clerk_session'] = 'cookie_token'
        
        config = ClerkConfig(self.env)
        token = self.authenticator._extract_token(req, config)
        self.assertEqual(token, 'cookie_token')
        
    def test_extract_token_from_authorization_header(self):
        """Test token extraction from Authorization header"""
        req = MockRequest(self.env)
        
        # Mock get_header method
        def mock_get_header(name):
            if name == 'Authorization':
                return 'Bearer header_token'
            return None
        req.get_header = mock_get_header
        
        config = ClerkConfig(self.env)
        token = self.authenticator._extract_token(req, config)
        self.assertEqual(token, 'header_token')


class ClerkLoginModuleTestCase(unittest.TestCase):
    
    def setUp(self):
        self.env = EnvironmentStub(enable=[ClerkLoginModule])
        self.env.config.set('clerk', 'secret_key', 'test_secret')
        self.env.config.set('clerk', 'signin_url', 'https://test.clerk.dev/sign-in')
        self.env.config.set('clerk', 'signout_url', 'https://test.clerk.dev/sign-out')
        self.login_module = ClerkLoginModule(self.env)
        
    def test_match_request_login_path(self):
        """Test that login path is matched"""
        req = MockRequest(self.env, path_info='/login')
        self.assertTrue(self.login_module.match_request(req))
        
    def test_match_request_logout_path(self):
        """Test that logout path is matched"""
        req = MockRequest(self.env, path_info='/logout')
        self.assertTrue(self.login_module.match_request(req))
        
    def test_match_request_callback_path(self):
        """Test that callback path is matched"""
        req = MockRequest(self.env, path_info='/clerk/callback')
        self.assertTrue(self.login_module.match_request(req))
        
    def test_navigation_items_shows_login_for_anonymous(self):
        """Test that login link is shown for anonymous users"""
        req = MockRequest(self.env)
        req.authname = 'anonymous'
        
        nav_items = list(self.login_module.get_navigation_items(req))
        
        # Should have login link
        login_items = [item for item in nav_items if item[1] == 'login']
        self.assertEqual(len(login_items), 1)
        self.assertEqual(login_items[0][0], 'metanav')
        self.assertEqual(login_items[0][2][0], 'Login')
        
    def test_navigation_items_shows_logout_for_authenticated(self):
        """Test that logout link is shown for authenticated users"""
        req = MockRequest(self.env)
        req.authname = 'user_123'
        
        nav_items = list(self.login_module.get_navigation_items(req))
        
        # Should have logout link
        logout_items = [item for item in nav_items if item[1] == 'logout']
        self.assertEqual(len(logout_items), 1)
        self.assertEqual(logout_items[0][0], 'metanav')
        self.assertEqual(logout_items[0][2][0], 'Logout')
        
    def test_login_link_displays_on_main_page(self):
        """Test that login link is visible in actual HTTP response - true integration test"""
        import urllib.request
        import urllib.error
        import time
        
        # Give server time to start if needed
        time.sleep(1)
        
        # Try to fetch the actual HTTP response from the running server
        try:
            with urllib.request.urlopen('http://127.0.0.1:9876/myproject', timeout=5) as response:
                html_content = response.read().decode('utf-8')
                
            print(f"\nActual HTML metanav content:")
            # Extract the metanav section
            if 'id="metanav"' in html_content:
                start = html_content.find('id="metanav"')
                end = html_content.find('</div>', start)
                metanav_section = html_content[start:end+6]
                print(metanav_section)
            else:
                print("No metanav found!")
                
            # Check for login link in the actual HTML
            has_login_link = 'href="/myproject/login"' in html_content or '>Login<' in html_content
            
            self.assertTrue(has_login_link, 
                           f"Login link should be visible in actual HTTP response HTML. "
                           f"Metanav contains: {metanav_section if 'metanav_section' in locals() else 'Not found'}")
                           
        except urllib.error.URLError as e:
            self.skipTest(f"Could not connect to test server: {e}. Server may not be running.")
        except Exception as e:
            self.fail(f"Error during HTTP test: {e}")
        
    def test_login_redirects_to_clerk(self):
        """Test that /login redirects to Clerk sign-in URL"""
        req = MockRequest(self.env, path_info='/login')
        req.args = {'next': '/tickets'}
        
        # Mock redirect to capture the URL
        redirect_url = None
        def mock_redirect(url):
            nonlocal redirect_url
            redirect_url = url
            raise RequestDone
        req.redirect = mock_redirect
        
        with self.assertRaises(RequestDone):
            self.login_module._handle_login(req, ClerkConfig(self.env))
            
        # Check redirect URL - should redirect to configured signin URL  
        self.assertIsNotNone(redirect_url)
        self.assertIn('sign-in?redirect_url=', redirect_url)
        
        # Parse the callback URL from redirect
        parsed = urllib.parse.urlparse(redirect_url)
        query_params = urllib.parse.parse_qs(parsed.query)
        callback_url = urllib.parse.unquote(query_params['redirect_url'][0])
        self.assertIn('/clerk/callback', callback_url)
        # Check that next parameter is in the callback URL (encoding may vary)
        self.assertTrue('next=/tickets' in callback_url or 'next=%2Ftickets' in callback_url)
        
    def test_login_fails_without_signin_url(self):
        """Test that login fails gracefully without sign-in URL configured"""
        req = MockRequest(self.env, path_info='/login')
        self.env.config.remove('clerk', 'signin_url')
        
        # Mock redirect to prevent RequestDone
        def mock_redirect(url):
            pass
        req.redirect = mock_redirect
        
        with self.assertRaises(TracError) as cm:
            self.login_module._handle_login(req, ClerkConfig(self.env))
        self.assertIn('CLERK_SIGNIN_URL not configured', str(cm.exception))
        
    @patch('trac.auth.clerk.Clerk')
    def test_callback_valid_session_token_sets_cookie_and_redirects(self, mock_clerk_class):
        """Test that valid session token in callback sets cookie and redirects"""
        req = MockRequest(self.env, path_info='/clerk/callback')
        req.args = {'session_token': 'valid_token', 'next': '/dashboard'}
        
        # Mock redirect to capture the URL
        redirect_url = None
        def mock_redirect(url):
            nonlocal redirect_url
            redirect_url = url
            raise RequestDone
        req.redirect = mock_redirect
        
        mock_clerk = Mock()
        mock_clerk_class.return_value = mock_clerk
        
        mock_session = Mock()
        mock_session.user_id = 'user_123'
        mock_clerk.sessions.verify_session.return_value = mock_session
        
        with self.assertRaises(RequestDone):
            self.login_module._handle_callback(req, ClerkConfig(self.env))
            
        # Check that cookie was set
        self.assertIn('clerk_session', req.outcookie)
        self.assertEqual(req.outcookie['clerk_session'].value, 'valid_token')
        
        # Check redirect
        self.assertEqual(redirect_url, '/dashboard')
        
    def test_callback_invalid_token_redirects_to_login(self):
        """Test that invalid token in callback redirects to login"""
        req = MockRequest(self.env, path_info='/clerk/callback')
        req.args = {'session_token': 'invalid_token'}
        
        # Mock redirect to capture the URL
        redirect_url = None
        def mock_redirect(url):
            nonlocal redirect_url
            redirect_url = url
            raise RequestDone
        req.redirect = mock_redirect
        
        with patch('trac.auth.clerk.Clerk') as mock_clerk_class:
            mock_clerk = Mock()
            mock_clerk_class.return_value = mock_clerk
            
            from clerk_backend_api import SDKError
            mock_clerk.sessions.verify_session.side_effect = SDKError('Invalid token')
            
            with self.assertRaises(RequestDone):
                self.login_module._handle_callback(req, ClerkConfig(self.env))
                
            # Should redirect to login
            self.assertIsNotNone(redirect_url)
            self.assertTrue(redirect_url.endswith('/login'))
            
    def test_callback_missing_token_redirects_to_login(self):
        """Test that missing session token redirects to login"""
        req = MockRequest(self.env, path_info='/clerk/callback')
        req.args = {}  # No session_token
        
        # Mock redirect to capture the URL
        redirect_url = None
        def mock_redirect(url):
            nonlocal redirect_url
            redirect_url = url
            raise RequestDone
        req.redirect = mock_redirect
        
        with self.assertRaises(RequestDone):
            self.login_module._handle_callback(req, ClerkConfig(self.env))
            
        # Should redirect to login
        self.assertIsNotNone(redirect_url)
        self.assertTrue(redirect_url.endswith('/login'))
        
    def test_logout_clears_cookie_and_redirects(self):
        """Test that logout clears cookie and redirects appropriately"""
        req = MockRequest(self.env, path_info='/logout')
        
        # Mock redirect to capture the URL
        redirect_url = None
        def mock_redirect(url):
            nonlocal redirect_url
            redirect_url = url
            raise RequestDone
        req.redirect = mock_redirect
        
        with self.assertRaises(RequestDone):
            self.login_module._handle_logout(req, ClerkConfig(self.env))
            
        # Check that cookie was cleared (set to empty with max-age=0)
        self.assertIn('clerk_session', req.outcookie)
        self.assertEqual(req.outcookie['clerk_session'].value, '')
        self.assertEqual(req.outcookie['clerk_session']['max-age'], '0')
        
        # Should redirect to Clerk sign-out URL
        self.assertIsNotNone(redirect_url)
        self.assertIn('sign-out?redirect_url=', redirect_url)


class ClerkSDKIntegrationTestCase(unittest.TestCase):
    """Tests that use the real SDK to catch method name errors"""
    
    def test_clerk_sdk_methods_exist(self):
        """Test that we're using the correct SDK methods - would catch AttributeError"""
        from clerk_backend_api import Clerk
        
        # Create a Clerk instance with a dummy key
        clerk = Clerk(bearer_auth='sk_test_dummy')
        
        # Test that the methods we use actually exist
        # This would have caught 'verify_session' not existing
        self.assertTrue(hasattr(clerk.sessions, 'verify'), 
                       "clerk.sessions should have 'verify' method, not 'verify_session'")
        self.assertFalse(hasattr(clerk.sessions, 'verify_session'),
                        "We're using 'verify_session' but it doesn't exist!")
        
        # Test clients.verify exists
        self.assertTrue(hasattr(clerk.clients, 'verify'),
                       "clerk.clients should have 'verify' method")
        
        # Test the actual method signatures match what we expect
        import inspect
        
        # Check sessions.verify signature
        sig = inspect.signature(clerk.sessions.verify)
        params = list(sig.parameters.keys())
        self.assertIn('request', params, "sessions.verify should accept 'request' parameter")
    
    def test_authenticator_with_real_sdk_structure(self):
        """Test authenticator using actual SDK structure - no mocks"""
        from clerk_backend_api import Clerk, SDKError
        
        env = EnvironmentStub()
        env.config.set('components', 'trac.auth.clerk.ClerkAuthenticator', 'enabled')
        env.config.set('clerk', 'secret_key', 'sk_test_dummy')
        env.config.set('clerk', 'debug', 'true')
        
        authenticator = ClerkAuthenticator(env)
        
        # Create a mock request with our cookie
        req = Mock()
        req.incookie = {'clerk_session': Mock(value='test_token')}
        req.get_header = Mock(return_value=None)
        
        # This should try to call clerk.sessions.verify (not verify_session)
        # and fail with SDKError due to invalid token, not AttributeError
        result = authenticator.authenticate(req)
        
        # We expect None (auth failed) not an AttributeError
        self.assertIsNone(result)
    
    def test_callback_handler_sdk_integration(self):
        """Test callback handler with real SDK - would catch method name errors"""
        from clerk_backend_api import Clerk
        
        env = EnvironmentStub()
        env.config.set('components', 'trac.auth.clerk.ClerkLoginModule', 'enabled')
        env.config.set('clerk', 'secret_key', 'sk_test_dummy')
        env.config.set('clerk', 'debug', 'true')
        
        login_module = ClerkLoginModule(env)
        
        # Mock request with callback parameters
        req = Mock()
        req.args = {'__clerk_db_jwt': 'test_token', 'next': '/'}
        req.href = lambda path='': f'/{path}'
        req.redirect = Mock()
        req.outcookie = {}
        
        cfg = ClerkConfig(env)
        
        # This should attempt to use the SDK and redirect to login on failure
        # NOT throw AttributeError
        try:
            login_module._handle_callback(req, cfg)
            # Should redirect to login due to invalid token
            req.redirect.assert_called()
            redirect_url = req.redirect.call_args[0][0]
            self.assertIn('login', redirect_url)
        except AttributeError as e:
            self.fail(f"Got AttributeError which means we're using wrong SDK method: {e}")


def test_suite():
    suite = unittest.TestSuite()
    suite.addTest(unittest.defaultTestLoader.loadTestsFromTestCase(ClerkConfigTestCase))
    suite.addTest(unittest.defaultTestLoader.loadTestsFromTestCase(ClerkAuthenticatorTestCase))
    suite.addTest(unittest.defaultTestLoader.loadTestsFromTestCase(ClerkLoginModuleTestCase))
    suite.addTest(unittest.defaultTestLoader.loadTestsFromTestCase(ClerkSDKIntegrationTestCase))
    return suite


if __name__ == '__main__':
    unittest.main(defaultTest='test_suite')