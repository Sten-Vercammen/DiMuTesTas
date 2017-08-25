from distutils.core import setup

import LittleDarwin
import License

setup(
    name='LittleDarwin',
    version=LittleDarwin.littleDarwinVersion,
    packages=['.', 'antlr4', 'antlr4.atn', 'antlr4.dfa', 'antlr4.error', 'antlr4.tree', 'antlr4.xpath'],
    license=License.returnLicense(),
    long_description=open('README').read(),

    url='www.parsai.net',
    author='Ali Parsai',
    author_email='ali@parsai.net',

    # allows for python -m LittleDarwin [options]
    entry_points={
    	'console_scripts': [
    		'LittleDarwin = LittleDarwin.__main__:main'
    	],
    }
)
