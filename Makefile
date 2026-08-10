.PHONY: run test lint migrate shell

run:
	docker-compose up --build

test:
	docker-compose run --rm web pytest --cov=outbound --cov=support --cov=orders --cov-report=term-missing

lint:
	docker-compose run --rm web sh -c "black --check . && flake8 ."

migrate:
	docker-compose run --rm web python manage.py migrate

shell:
	docker-compose run --rm web python manage.py shell
