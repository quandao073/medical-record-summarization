export interface ModelOption {
  value: string;   // "provider:model" format
  label: string;   // display name
}

export interface ModelGroup {
  label: string;
  options: ModelOption[];
}

export const MODEL_GROUPS: ModelGroup[] = [
  {
    label: "OpenAI",
    options: [
      { value: "openai:gpt-4o-mini", label: "gpt-4o-mini" },
      { value: "openai:gpt-4o", label: "gpt-4o" },
    ],
  },
  {
    label: "LM Studio (Local)",
    options: [
      { value: "lmstudio:meta-llama-3.1-8b-instruct", label: "Llama 3.1 8B" },
      { value: "lmstudio:qwen/qwen3.5-9b", label: "Qwen 3.5 9B" },
      { value: "lmstudio:qwen2.5-7b-instruct", label: "Qwen 2.5 7B" },
      { value: "lmstudio:google/gemma-4-e4b", label: "Gemma 4 E4B" },
    ],
  },
];

export const DEFAULT_MODEL = "openai:gpt-4o-mini";
