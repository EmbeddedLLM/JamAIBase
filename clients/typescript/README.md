<p align="center">
  <img width="70" src="https://i.ibb.co/CzpJcYG/jamai-logo.png" alt="jamai-logo">
</p>

<h1 align="center">JamAI</h1>

<p align="center">
  <a href="https://www.jamaibase.com">www.jamaibase.com</a>
</p>

<h2 align="center">This is a TS/JS Client Library for JamAIBase.</h2>

<p align="center">
  <a href="https://github.com/EmbeddedLLM/jamaisdk">GitHub</a> |
  <a href="https://docs.jamaibase.com/">Documentation</a> |
  <a href="https://embeddedllm.github.io/jamaisdk-ts-docs/classes/APIClient.html">TS/JS API Documentation</a> |
  <a href="https://github.com/EmbeddedLLM/jamaisdk/issues">Issues</a> |
  <a href="https://www.npmjs.com/package/jamaibase">NPM Package</a>
</p>

## Introduction
JamAI Base: Let Your Database Orchestrate LLMs and RAG

This is a TS/JS Client Library for JamAIBase.

There are three types of LLM powered database tables (GenTable):

-   Action Table
-   Chat Table
-   Knowledge Table

### Innovative RAG Techniques: 
- __Effortless RAG__: Get up-to-date RAG features built right into the system. No need to build the RAG pipeline yourself. 
- __Query Rewriting__: Boosts the accuracy and relevance of your search queries. 
- __Hybrid Search & Reranking__: Combines keyword-based search, structured search, and vector search for the best results. 
- __Structured RAG Content Management__: Organizes and manages your structured content seamlessly. 
- __Adaptive Chunking__: Automatically determines the best way to chunk your data, avoiding unnecessary splits in tables. 
- __BGE M3-Embedding__: Leverages multi-lingual, multi-functional, and multi-granular text embeddings for free. 

## Installation

```bash
npm install jamaibase@latest
```

## Usage

### Create API Client

Create an API client with baseURL:

```javascript
import JamAI from "jamaibase";

const jamai = new JamAI({ baseURL: "http://localhost:5173/" });
```

Create an API client with api key and project id:

```javascript
import JamAI from "jamaibase";

const jamai = new JamAI({ apiKey: "jamai_apikey", projectId: "proj_id" });
```

Create an API client with custom HTTP client:

```javascript
import axios from "axios";
import JamAI from "jamaibase";

const username = "user";
const password = "password";

const credentials = Buffer.from(`${username}:${password}`).toString("base64");

const httpClient = axios.create({
    headers: {
        Authorization: `Basic ${credentials}`,
        "Content-Type": "application/json"
    }
});

const jamai = new JamAI({
    baseURL: "https://app.jamaibase.com",
    httpClient: httpClient
});
```

Create an API client with basic authorization credentials:

```javascript
import JamAI from "jamaibase";

const jamai = new JamAI({
    baseURL: "https://app.jamaibase.com",
    credentials: {
        username: "your-username",
        password: "your-password"
    }
});
```

Create an API client with maxretry and timeout:

```javascript
import JamAI from "jamaibase";

const jamai = new JamAI({
    baseURL: "https://app.jamaibase.com",
    maxRetries: 3,
    timeout: 500
});
```

Configure httpAgent/ httpsAgent:

```javascript
import JamAI from "jamaibase";

const jamai = new JamAI({
    baseURL: "https://app.jamaibase.com"
});

jamai.setHttpagentConfig({
    maxSockets: 100,
    maxFreeSockets: 10,
    freeSocketTimeout: 30000 // free socket keepalive for 30 seconds
});
```

Can be imported from different modules depending on the need:

```javascript
import JamAI from "jamaibase/index.umd.js";
```

### Types

Types can be imported from resources:

```javascript
import { ChatRequest } from "jamaibase/resources/llm/chat";

let response: ChatRequest;
```

### Use client object to call the methods

Example of adding a row to action table:

```javascript
try {
    const response = await jamai.addRow({
        table_type: "action",
        table_id: "workout-suggestion",
        data: {
            age: 30,
            height_in_centimeters: 170,
            weight_in_kg: 60
        }
    });
    console.log("response: ", response);
} catch (err) {
    console.error(err.message);
}
```

Example of adding row with streaming output

```javascript
try {
    const stream = await jamai.addRowStream({
        table_type: "action",
        table_id: "action-table-example-1",
        data: {
            Name: "Albert Eistein"
        }
    });

    const reader = stream.getReader();

    while (true) {
        const { done, value } = await reader.read();
        if (done) {
            console.log("Done");
            break;
        }
        console.log(value);
        if (value) {
            console.log(value?.choices[0]?.message.content);
        }
    }
} catch (err) {}
```

## Constructor Parameters for APIClient Configuration

| Parameter    | Type                  | Description                                    | Default Value               | Required / Optional         |
| ------------ | --------------------- | ---------------------------------------------- | --------------------------- | --------------------------- |
| `baseURL`    | `string`              | Base URL for the API requests.                 | `https://app.jamaibase.com` | optional                    |
| `maxRetries` | `number`              | Maximum number of retries for failed requests. | 0                           | Optional                    |
| `httpClient` | `AxiosInstance`       | Axios instance for making HTTP requests.       | `AxiosInstance`             | Optional                    |
| `timeout`    | `number \| undefined` | Timeout for the requests.                      | `undefined`                 | Optional                    |
| `apiKey`     | `string \| undefined` | apiKey.                                        | `undefined`                 | Rqruired if accessing cloud |
| `projectId`  | `string \| undefined` | projectId.                                     | `undefined`                 | Optional if accessing cloud |

## Quick Start Guide

### React JS

To integrate JamAI into a React application, follow these steps:

2.  Install React and Create a New Project

```bash
    npx create-react-app my-app
    cd my-app
```

2.  Install jamai

```bash
    npm install jamai
```

3. Create and Use the JamAI Client in your React component

```javascript
// pages/index.js

import { useEffect, useState } from "react";

export default function Home() {
    const [tableData, setTableData] = useState([]);

    useEffect(() => {
        const fetchData = async () => {
            try {
                const response = await yourClient.listTables({
                    table_type: "action"
                });
                setTableData(response.items);
            } catch (err) {
                    console.error(err.message);
            }
            }
        };
        fetchData();
    }, []);

    return (
        <div>
            <h1>List of Tables</h1>
            <ul>
                {tableData.map((table) => (
                    <li key={table.id}>
                        <h2>Table ID: {table.id}</h2>
                        <h3>Columns:</h3>
                        <ul>
                            {table.cols.map((column) => (
                                <li key={column.id}>
                                    <p>ID: {column.id}</p>
                                    <p>Data Type: {column.dtype}</p>
                                    {/* Render other properties as needed */}
                                </li>
                            ))}
                        </ul>
                    </li>
                ))}
            </ul>
        </div>
    );
}
```

### Next JS

To integrate JamAI into a Next.js application, follow these steps:

1.  Install Next.js and Create a New Project

```bash
    npx create-next-app@latest my-app
    cd my-app
```

2.  Install jamaibase

```bash
    npm install jamaibase
```

3. First, create an API route in your Next.js project

```javascript
// pages/api/listTables.js

import { NextApiRequest, NextApiResponse } from "next";
import JamAI from "jamaibase";

export default async function handler(req: NextApiRequest, res: NextApiResponse) {
    const jamai = new JamAI({ baseURL: "http://localhost:5173/" });
    try {
        const response = await yourClient.listTables({
            table_type: "action"
        });
        res.status(200).json(response);
    } catch (error) {
        console.error("Error fetching tables:", error);
        res.status(500).json({ message: "Internal server error" });
    }
}
```

4. Then, in your Next.js component, you can fetch this data from the API route and render it:

```javascript
// pages/index.js

import { useEffect, useState } from "react";

export default function Home() {
    const [tableData, setTableData] = useState([]);

    useEffect(() => {
        const fetchData = async () => {
            try {
                const response = await fetch("/api/listTables");
                if (response.ok) {
                    const data = await response.json();
                    setTableData(data.items);
                } else {
                    console.error("Failed to fetch data:", response.statusText);
                }
            } catch (error) {
                console.error("Error fetching data:", error);
            }
        };
        fetchData();
    }, []);

    return (
        <div>
            <h1>List of Tables</h1>
            <ul>
                {tableData.map((table) => (
                    <li key={table.id}>
                        <h2>Table ID: {table.id}</h2>
                        <h3>Columns:</h3>
                        <ul>
                            {table.cols.map((column) => (
                                <li key={column.id}>
                                    <p>ID: {column.id}</p>
                                    <p>Data Type: {column.dtype}</p>
                                    {/* Render other properties as needed */}
                                </li>
                            ))}
                        </ul>
                    </li>
                ))}
            </ul>
        </div>
    );
}
```

### SvelteKit

1. Setup SvelteKit Project

```bash
npm create svelte@latest my-app
cd my-app
npm install
```

2. Install JamAI

```bash
npm i jamaibase
```

3. reate a new file src/routes/create-table.svelte and add the following code:

```javascript
<script>
    import { onMount } from 'svelte';
    import JamAI from 'jamaibase';
    import { writable } from 'svelte/store';

    const jamai = new JamAI({ baseURL: "http://localhost:5173/" });

    let colId = '';
    let colDtype = '';


    const responseStore = writable(null);
    const errorStore = writable(null);

    const addColumn = () => {
        columns = [{ id: colId, dtype: colDtype}];
        colId = '';
        colDtype = '';
    };

    const createActionTable = async () => {
        try {
            const response = await jamai.createActionTable({
                id: tableName,
                cols: columns,
            });
            responseStore.set(response);
            errorStore.set(null);
        } catch (error) {
            errorStore.set(error.message);
            responseStore.set(null);
        }
    };
</script>

<style>
    input, select {
        margin: 0.5rem;
        padding: 0.5rem;
    }

    button {
        margin: 0.5rem;
        padding: 0.5rem 1rem;
    }
</style>

<main>
    <h1>Create Action Table</h1>

    <div>
        <label>
            Table Name:
            <input type="text" bind:value={tableName} />
        </label>
    </div>

    <div>
        <label>
            Column ID:
            <input type="text" bind:value={colId} />
        </label>
        <label>
            Column Data Type:
            <select bind:value={colDtype}>
                <option value="int">Integer</option>
                <option value="str">String</option>
                <!-- Add other data types as needed -->
            </select>
        </label>
    </div>


    <button on:click={addColumn}>Add Column</button>
    <button on:click={createActionTable}>Create Table</button>
</main>

```

##
