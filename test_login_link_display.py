#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Test to verify that the Clerk login link is displayed on the main Trac page.
"""

import sys
import os
sys.path.insert(0, '.')

from trac.env import Environment
from trac.test import MockRequest
from trac.web.chrome import Chrome
from trac.auth.clerk import ClerkLoginModule

def test_login_link_display():
    """Test that login link appears in navigation for anonymous users"""
    print("Testing login link display...")
    
    # Create environment with Clerk enabled
    env = Environment('../myproject')
    
    # Create mock request for anonymous user
    req = MockRequest(env)
    req.authname = 'anonymous'
    
    # Get navigation items from ClerkLoginModule
    login_module = env[ClerkLoginModule]
    nav_items = list(login_module.get_navigation_items(req))
    
    print(f"Found {len(nav_items)} navigation items from ClerkLoginModule:")
    for category, name, item in nav_items:
        print(f"  - {category}.{name}: {item}")
    
    # Check for login item
    login_items = [item for item in nav_items if item[1] == 'login']
    
    if login_items:
        print("✓ Login link found!")
        login_item = login_items[0]
        print(f"  Category: {login_item[0]}")
        print(f"  Name: {login_item[1]}")
        print(f"  Label: {login_item[2][0]}")
        print(f"  URL: {login_item[2][1]}")
        return True
    else:
        print("✗ Login link NOT found!")
        return False

def test_with_chrome():
    """Test navigation rendering through Chrome (full pipeline)"""
    print("\nTesting with Chrome navigation rendering...")
    
    env = Environment('../myproject')
    req = MockRequest(env)
    req.authname = 'anonymous'
    
    # Get Chrome instance
    chrome = Chrome(env)
    
    # Get all navigation items (this is what actually renders in the UI)
    nav = {}
    for contributor in chrome.navigation_contributors:
        for category, name, item in contributor.get_navigation_items(req) or []:
            nav.setdefault(category, []).append((name, item))
    
    print("All navigation items:")
    for category, items in nav.items():
        print(f"  {category}:")
        for name, item in items:
            print(f"    - {name}: {item}")
    
    # Check for login in metanav
    metanav = nav.get('metanav', [])
    login_items = [item for name, item in metanav if name == 'login']
    
    if login_items:
        print("✓ Login link found in metanav!")
        return True
    else:
        print("✗ Login link NOT found in metanav!")
        return False

if __name__ == '__main__':
    print("=" * 60)
    print("CLERK LOGIN LINK DISPLAY TEST")
    print("=" * 60)
    
    try:
        result1 = test_login_link_display()
        result2 = test_with_chrome()
        
        print("\n" + "=" * 60)
        if result1 and result2:
            print("✓ ALL TESTS PASSED: Login link is properly displayed!")
            sys.exit(0)
        else:
            print("✗ TESTS FAILED: Login link is not being displayed correctly!")
            sys.exit(1)
            
    except Exception as e:
        print(f"✗ TEST ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)