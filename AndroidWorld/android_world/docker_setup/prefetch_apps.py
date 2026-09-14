"""Pre-downloads all app APKs used by android_world's device setup.

android_world lazily downloads each app's APK (from a GCS bucket) into a
local cache directory the first time the emulator is set up. If that happens
at container *run* time, a network blip during download makes the whole
container fail to start.

This script downloads every APK referenced by
`android_world.env.setup_device.apps` into that same local cache directory
(`{tempdir}/android_world/app_data`) so it can be run once at Docker *build*
time. At container run time, `apps.download_app_data` will find the files
already cached and skip the network call entirely.
"""

import inspect
import logging
import sys

from android_world.env.setup_device import apps

logging.basicConfig(level=logging.INFO)


def _iter_apk_names():
  """Yields every unique apk_name referenced by an AppSetup subclass."""
  seen = set()
  for _, obj in inspect.getmembers(apps, inspect.isclass):
    if obj is apps.AppSetup or not issubclass(obj, apps.AppSetup):
      continue
    for apk_name in obj.apk_names:
      if apk_name and apk_name not in seen:
        seen.add(apk_name)
        yield apk_name


def main() -> int:
  apk_names = sorted(_iter_apk_names())
  logging.info('Prefetching %d APKs...', len(apk_names))

  failures = []
  for name in apk_names:
    try:
      path = apps.download_app_data(name)
      logging.info('Cached %s -> %s', name, path)
    except Exception as e:  # pylint: disable=broad-except
      logging.error('Failed to prefetch %s: %s', name, e)
      failures.append(name)

  if failures:
    logging.error('Failed to prefetch %d/%d APKs: %s', len(failures),
                   len(apk_names), failures)
    return 1

  logging.info('Done prefetching %d APKs.', len(apk_names))
  return 0


if __name__ == '__main__':
  sys.exit(main())
