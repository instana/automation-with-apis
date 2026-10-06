#!/usr/bin/env python3
"""Test runner script for the configuration migration project."""

import subprocess
import sys
import os
import re


def run_tests():
    """Run all unit tests and provide a summary."""
    print("🧪 Running Unit Tests for Configuration Migration Project")
    print("=" * 60)
    
    # Change to the directory of this script
    os.chdir(os.path.dirname(os.path.abspath(__file__)))

    # Set up environment
    env = os.environ.copy()
    env['PYTHONPATH'] = '.'
    
    # Test files to run
    test_files = [
        'tests/test_utils.py',
        'tests/test_config.py',
        'tests/test_config_class.py',
        'tests/test_cli.py',
        'tests/test_events_migrator.py',
        'tests/test_alert_channels_migrator.py',
        'tests/test_alert_configs_migrator.py',
        'tests/test_custom_dashboards_migrator.py',
        'tests/test_custom_dashboards_migrator_async.py',
        'tests/test_maintenance_configs_migrator.py',
        'tests/test_website_configs_migrator.py',
        'tests/test_application_configs_migrator.py',
        'tests/test_service_configs_migrator.py',
        'tests/test_endpoint_configs_migrator.py',
        'tests/test_base_smart_alerts_migrator.py',
        'tests/test_infrastructure_smart_alerts_migrator.py',
        'tests/test_permissions.py',
        'tests/test_rate_limiter_and_async_client.py',
        'tests/test_smart_alerts_dry_run.py',
        'tests/test_synthetic_configs_migrator.py',
        'tests/test_synthetic_smart_alerts_migrator.py'
    ]
    
    total_passed = 0
    total_failed = 0
    results = {}
    
    for test_file in test_files:
        print(f" 📋 Running tests in {test_file}...")
        try:
            result = subprocess.run(
                ['uv', 'run', 'pytest', test_file, '-v', '--tb=short'],
                env=env,
                capture_output=True,
                text=True
            )
            
            if result.returncode == 0:
                print(f"✅ {test_file} - PASSED")
                total_passed += 1
                results[test_file] = "PASSED"
            else:
                print(f"❌ {test_file} - FAILED")
                if result.stdout:
                    print(result.stdout)
                if result.stderr:
                    print(result.stderr)
                total_failed += 1
                results[test_file] = "FAILED"
                
        except Exception as e:
            print(f"❌ {test_file} - ERROR: {e}")
            total_failed += 1
            results[test_file] = f"ERROR: {e}"
    
    # Summary
    print("\n" + "=" * 60)
    print("📊 TEST SUMMARY")
    print("=" * 60)
    
    for test_file, status in results.items():
        status_icon = "✅" if status == "PASSED" else "❌"
        print(f"{status_icon} {test_file}: {status}")
    
    print(f"\n📈 Total Results:")
    print(f"   ✅ Passed: {total_passed}")
    print(f"   ❌ Failed: {total_failed}")
    print(f"   📊 Total: {total_passed + total_failed}")
    
    if total_failed == 0:
        print("\n🎉 All tests passed!")
        
        # Run full coverage across all source modules
        print("\n" + "=" * 60)
        print("📊 COVERAGE REPORT")
        print("=" * 60)

        try:
            coverage_result = subprocess.run([
                'uv', 'run', 'pytest', 'tests/',
                '--cov=.',
                '--cov-report=term-missing',
                '--cov-report=html:htmlcov',
            ], env=env, capture_output=True, text=True)

            if coverage_result.returncode in [0, 1]:
                print("✅ Coverage report generated successfully!")
                print("\n📁 HTML coverage report saved to: htmlcov/index.html")

                # Extract and display per-file coverage + TOTAL line
                lines = coverage_result.stdout.split('\n')
                in_table = False
                table_lines = []
                for line in lines:
                    if line.startswith('Name') and 'Stmts' in line:
                        in_table = True
                    if in_table:
                        table_lines.append(line)
                    if in_table and line.startswith('TOTAL'):
                        break

                if table_lines:
                    print("\n📋 Coverage by module:")
                    for tl in table_lines:
                        print(f"   {tl}")
                else:
                    # Fallback: just print the TOTAL line
                    for line in lines:
                        if 'TOTAL' in line and '%' in line:
                            print(f"\n📈 Overall Coverage: {line.strip()}")
                            break
            else:
                print("⚠️  Coverage report generation failed")
                print(f"Error: {coverage_result.stderr}")

        except Exception as e:
            print(f"⚠️  Coverage report error: {e}")
        
        return 0
    else:
        print(f"\n⚠️  {total_failed} test(s) failed. Please check the output above.")
        return 1


if __name__ == "__main__":
    sys.exit(run_tests())
