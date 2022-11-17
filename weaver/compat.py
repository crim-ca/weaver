from typing import Tuple, Union

# pylint: disable=unused-import
try:
    from packaging.version import _Version, InvalidVersion, Version as PackageVersion  # noqa

    class Version(PackageVersion):
        @property
        def version(self) -> Tuple[Union[int, str], ...]:
            parts = [part for part in self._version[1:] if part is not None]
            parts = tuple(part_group for part in parts for part_group in part)
            return parts

        @property
        def patch(self):
            return self.micro

except ImportError:
    from distutils.version import LooseVersion as BaseVersion  # pylint: disable=deprecated-module

    InvalidVersion = ValueError

    class Version(BaseVersion):
        @property
        def major(self) -> int:
            num = self.version[0:1]
            return int(num[0]) if num else None

        @property
        def minor(self) -> int:
            num = self.version[1:2]
            return int(num[0]) if num else None

        @property
        def patch(self) -> int:
            num = self.version[2:3]
            return int(num[0]) if num else None

        @property
        def micro(self) -> int:
            return self.patch
