#!/usr/bin/env python3
"""
Test script for Bright Data Support
Demonstrates HTTPS tunneling issue with ISP and Datacenter proxies

Issue: 403 Forbidden on HTTPS tunnel connections
Customer: brd-customer-hl_203e325d
Zones affected: zone-isp_proxy_sa, zone-datacenter_proxy_sa
"""
import requests
import warnings
warnings.filterwarnings('ignore', message='Unverified HTTPS request')

print("=" * 70)
print("BRIGHT DATA PROXY TESTING - HTTPS TUNNELING ISSUE")
print("Customer: brd-customer-hl_203e325d")
print("=" * 70)

# Test configurations
proxies_to_test = [
    {
        'name': 'ISP Proxy',
        'url': 'http://brd-customer-hl_203e325d-zone-isp_proxy_sa:mscsvy8mi031@brd.superproxy.io:33335'
    },
    {
        'name': 'Datacenter Proxy', 
        'url': 'http://brd-customer-hl_203e325d-zone-datacenter_proxy_sa:nlk4ksab3325@brd.superproxy.io:33335'
    }
]

test_sites = [
    ('Bright Data Test (HTTP)', 'http://lumtest.com/myip.json'),
    ('Saudi Gov Site (HTTPS)', 'https://uqn.gov.sa/category?cat=10'),
]

for proxy_config in proxies_to_test:
    print(f"\n{'=' * 70}")
    print(f"Testing: {proxy_config['name']}")
    print(f"Zone: {proxy_config['url'].split('@')[0].split(':')[1].split('-zone-')[1]}")
    print('=' * 70)
    
    proxies = {
        'http': proxy_config['url'],
        'https': proxy_config['url']
    }
    
    for site_name, url in test_sites:
        print(f"\n[Test] {site_name}")
        print(f"URL: {url}")
        print("-" * 70)
        
        try:
            response = requests.get(
                url,
                proxies=proxies,
                timeout=30,
                verify=False,
                headers={
                    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)',
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                }
            )
            
            print(f"✅ SUCCESS")
            print(f"   Status Code: {response.status_code}")
            print(f"   Content Length: {len(response.text)} bytes")
            
            if url.startswith('http://lumtest'):
                try:
                    data = response.json()
                    print(f"   IP: {data.get('ip')}")
                    print(f"   Country: {data.get('country')} ({data.get('country_code')})")
                except:
                    pass
                    
        except requests.exceptions.ProxyError as e:
            print(f"❌ PROXY ERROR")
            print(f"   Error: {str(e)[:200]}")
            if '403 Forbidden' in str(e):
                print(f"   → This is the HTTPS tunneling issue!")
                
        except requests.exceptions.Timeout:
            print(f"⚠️  TIMEOUT")
            print(f"   Request timed out after 30 seconds")
            
        except Exception as e:
            print(f"❌ ERROR: {type(e).__name__}")
            print(f"   Details: {str(e)[:200]}")

print("\n" + "=" * 70)
print("SUMMARY")
print("=" * 70)
print("EXPECTED BEHAVIOR:")
print("  • HTTP requests should work (lumtest.com) ✅")
print("  • HTTPS requests should work (uqn.gov.sa) ❌ Currently failing")
print("\nACTUAL BEHAVIOR:")
print("  • HTTP requests work correctly")
print("  • HTTPS requests fail with '403 Forbidden - Tunnel connection failed'")
print("\nREQUEST:")
print("  Please enable HTTPS tunneling for these proxy zones")
print("=" * 70)