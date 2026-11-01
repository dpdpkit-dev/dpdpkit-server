import { createAppFromEnv } from "./app.js";

const port = Number(process.env.PORT ?? 3000);
createAppFromEnv().listen(port, () => console.log(`example app on http://localhost:${port}`));
