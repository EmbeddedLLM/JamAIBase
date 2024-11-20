const fs = require("fs");

// Path to the tsconfig.json file
const tsConfigPath = "./tsconfig.json";

// Read the tsconfig.json file
fs.readFile(tsConfigPath, "utf8", (err, data) => {
    if (err) {
        console.error(`Error reading the file: ${err}`);
        return;
    }

    try {
        // Parse the JSON data
        const tsConfig = JSON.parse(data);

        // Check if the "include" field exists and is an array
        if (!Array.isArray(tsConfig.include)) {
            tsConfig.include = []; // If "include" doesn't exist, create it as an empty array
        }

        // Check if "__tests__" is already in the array
        if (!tsConfig.include.includes("__tests__")) {
            // Add "__tests__" to the "include" array
            tsConfig.include.push("__tests__");
        }

        // Convert the modified object back to JSON
        const updatedTsConfig = JSON.stringify(tsConfig, null, 2);

        // Write the updated JSON back to the file
        fs.writeFile(tsConfigPath, updatedTsConfig, "utf8", (err) => {
            if (err) {
                console.error(`Error writing the file: ${err}`);
                return;
            }

            console.log("tsconfig.json has been updated successfully (include '__tests__' folder.)");
        });
    } catch (err) {
        console.error(`Error parsing JSON: ${err}`);
    }
});
