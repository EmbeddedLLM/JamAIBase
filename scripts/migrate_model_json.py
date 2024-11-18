import json
import sys

from owl.protocol import ModelListConfig


def transform_json(original_json):
    new_json = {"llm_models": [], "embed_models": [], "rerank_models": []}
    ellm_json = {"llm_models": [], "embed_models": [], "rerank_models": []}
    for config_type in ["llm_models", "embed_models", "rerank_models"]:
        configs = original_json.get(config_type, [])
        for config in configs:
            if config.get("deployments", None) is None:
                # Extract the provider from the id
                provider, _ = config["id"].split("/", 1)

                # Create the ModelDeploymentConfig instance
                deployment_config = {
                    "litellm_id": config.get("litellm_id", ""),
                    "api_base": config.get("api_base", ""),
                    "provider": provider,
                }
                # Create the ModelConfig instance
                model_config = {
                    k: v
                    for k, v in config.items()
                    if k not in ["litellm_id", "api_base", "provider", "internal_only"]
                }
                model_config["deployments"] = [deployment_config]

            else:
                model_config = config
            if config.get("internal_only", False):
                ellm_json[config_type].append(model_config)
            else:
                new_json[config_type].append(model_config)
    val = ModelListConfig.model_validate(new_json)
    print(val)
    val = ModelListConfig.model_validate(ellm_json)
    print(val)
    return new_json, ellm_json


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python migrate_model_json.py <original_json>")
        sys.exit(1)
    original_json_path = sys.argv[1]
    with open(original_json_path, "r") as f:
        original_json = json.load(f)
    transformed_json, internal_json = transform_json(original_json)
    with open(original_json_path, "w") as f:
        f.write(json.dumps(transformed_json, indent=4))
    if sum([len(internal_json[x]) for x in internal_json.keys()]) > 0:
        with open(f"{original_json_path.split('.json')[0]}_internal.json", "w") as f:
            f.write(json.dumps(internal_json, indent=4))
