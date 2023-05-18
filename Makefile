.PHONY : test generate_test_files serve_tests conan_install_linux



serve_tests:
	poetry run python -m tests.scripts.tests_server

generate_test_files:
	poetry run python -m tests.test_codegen.testcases

test:
	pytest tests --cov=qtgql --cov-report=xml --cov-append

conan_install_linux:
	poetry run conan install . -s build_type=Debug -pr profiles/linux  --build=missing
