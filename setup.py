from setuptools import setup, find_packages

setup(name='khirolib',
        version='0.0.3',
        description='Kawasaki robot control with Py',
        packages=find_packages(include=[
            'khirolib',
            'khirolib.*'
        ]),
        python_requires=">=3.8",
        install_requires=[]
)
