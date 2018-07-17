import setuptools

with open("README.rst") as f:
    long_description = f.read()

setuptools.setup(
    name="mocksh",
    py_modules=["mocksh"],
    version="0.0.1",
    author="Jan Verbeek",
    author_email="jan.verbeek@posteo.nl",
    description="Simple shell-style process calling",
    long_description=long_description,
    long_description_content_type='text/x-rst',
    url="https://github.com/blyxxyz/mocksh",
    license="ISC",
    classifiers=[
        "Topic :: System :: System Shells",
        "Intended Audience :: Developers",
        "Intended Audience :: System Administrators",
        "Environment :: Console",
        "Programming Language :: Python",
        "Programming Language :: Python :: 2",
        "Programming Language :: Python :: 2.7",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.4",
        "Programming Language :: Python :: 3.5",
        "Programming Language :: Python :: 3.6",
        "Programming Language :: Python :: 3.7",
        "Programming Language :: Python :: Implementation :: CPython",
        "Programming Language :: Python :: Implementation :: PyPy",
        "License :: OSI Approved :: ISC License (ISCL)",
    ]
)
