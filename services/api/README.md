# JamAI Base API service

## Note for VSCode Users

In order for Ruff settings to apply correctly, you must open the repo folder directly via `Open Folder...` instead of as a `Workspace`. Workspace does not work correctly for some unknown reason.

## Getting Started

1. Create an environment `.env` file. You can modify it from the provided `.env.example` file.
2. Start the services using Docker Compose. Depending on your needs, you can choose to either start everything or excluding the API server `owl` (for easier dev work, for example).

   - Launch all services
     ```bash
     docker compose -p jm --env-file .env -f docker/compose.dev.yml up --quiet-pull
     ```
   - Launch all except `owl`, `frontend`
     ```bash
     docker compose -p jm --env-file .env -f docker/compose.dev.yml up --quiet-pull -d --scale owl=0 --scale frontend=0
     ```

3. If you choose to launch `owl` manually, then run these steps to setup your environment

   1. Create a Python 3.12 environment and install `owl` (here we use [micromamba](https://mamba.readthedocs.io/en/latest/user_guide/micromamba.html) but you can use other tools such as [conda](https://conda.io/projects/conda/en/latest/user-guide/getting-started.html), virtualenv, etc):

      ```bash
      micromamba create -n jamai312 python=3.12 -y
      micromamba activate jamai312
      cd services/api
      python -m pip install -e .
      ```

   2. Uncomment the "Service connection" section of `.env.example` and copy them into your `.env` file.
   3. Start `owl`.

      ```bash
      OWL_WORKERS=2 OTEL_PYTHON_FASTAPI_EXCLUDED_URLS="api/health" OTEL_INSTRUMENTATION_HTTP_CAPTURE_HEADERS_SERVER_REQUEST='X-.*' python -m owl.entrypoints.api

      # Delete existing DB data, start owl
      OWL_DB_RESET=1 OWL_WORKERS=2 OTEL_PYTHON_FASTAPI_EXCLUDED_URLS="api/health" OTEL_INSTRUMENTATION_HTTP_CAPTURE_HEADERS_SERVER_REQUEST='X-.*' python -m owl.entrypoints.api
      ```

4. To run Stripe tests:
   1. Add Stripe API keys into `.env`:
      - `OWL_STRIPE_API_KEY`
      - `OWL_STRIPE_PUBLISHABLE_KEY_TEST`
      - `OWL_STRIPE_WEBHOOK_SECRET_TEST`
   2. Run Stripe event forwarding `stripe listen --forward-to localhost:6969/api/v2/organizations/webhooks/stripe --api-key <stripe_api_key>`

<!-- prettier-ignore-start -->

> [!TIP]
> - You can launch the Docker services in background mode by appending `-d --wait`
> - You can rebuild the `owl` image by appending `--build --force-recreate owl`

<!-- prettier-ignore-end -->

## Backend Dev Tips

- How to run tests (can refer to `.github/workflows/ci.yml` for more info)

  1. Launch services via `compose.dev.yml` by following the steps above
  2. `pytest services/api/tests`

<!-- prettier-ignore-start -->

> [!TIP]
> - Run all tests except those that require on-prem setup: `pytest services/api/tests -m "not onprem"`
> - Run a specific test or a subset: `pytest services/api/tests -k <test_name>`

<!-- prettier-ignore-end -->

- How to have your code reflected in the Docker environment

  1. Launch services via `compose.dev.yml` by following the steps above
  2. Modify backend code
  3. Restart `owl` by issuing: `docker compose -p jm --env-file .env -f docker/compose.ci.yml restart owl`
