from setuptools import find_packages, setup


package_name = "gradua"


setup(
    name=package_name,
    version="0.0.1",
    packages=find_packages(exclude=["test"]),
    data_files=[
        ("share/ament_index/resource_index/packages", [f"resource/{package_name}"]),
        (f"share/{package_name}", ["package.xml"]),
        (
            f"share/{package_name}/launch",
            [
                "launch/camera_preview.launch.py",
                "launch/undistort_preview.launch.py",
            ],
        ),
    ],
    install_requires=["setuptools"],
    zip_safe=True,
    maintainer="lsx",
    maintainer_email="lsx@example.com",
    description="Minimal ROS2 camera preview package for direct USB camera preview.",
    license="Apache-2.0",
    tests_require=["pytest"],
    entry_points={
        "console_scripts": [
            "camera_preview = gradua.camera_preview_node:main",
            "undistort_preview = gradua.undistort_preview_node:main",
        ],
    },
)
