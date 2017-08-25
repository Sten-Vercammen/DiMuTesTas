from distutils.core import setup

setup(
    name='tasKIT',
    version='0.2',
    packages=['.'],
    long_description="Enables task processing",

    author='Sten Vercammen',
    author_email='sten.vercammen@gmail.com',

    install_requires=[
        'pika'
    ]
)