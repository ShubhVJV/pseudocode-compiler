# Pseudocode to Java Code Generator

An AI-powered tool that converts **human-readable pseudocode into valid Java code**.

The goal of this project is to allow users to write pseudocode using a flexible, natural syntax and automatically generate executable Java code from it.

## 🚀 Project Overview

Traditional programming requires users to follow strict programming language syntax. This project aims to bridge the gap between **problem-solving ideas written in pseudocode** and actual implementation.

The system will:

1. Accept pseudocode written in a flexible format.
2. Understand the intent and structure of the pseudocode.
3. Convert the pseudocode into valid Java code.
4. Preserve explicitly mentioned programming constructs, functions, and imports.
5. Produce readable and executable Java code.

### Example

**Input:**

```text
Start

Import ArrayList

Create an ArrayList called numbers

Add 10, 20 and 30 to numbers

For each number in numbers:
    Print number

End
```

**Generated Java:**

```java
import java.util.ArrayList;

import java.util.*;

public class Main {
    public static void main(String[] args) {

        ArrayList<Integer> numbers = new ArrayList<>();

        numbers.add(10);
        numbers.add(20);
        numbers.add(30);

        for (int number : numbers) {
            System.out.println(number);
        }
    }
}
```

## 🎯 Objectives

* Develop a flexible pseudocode grammar.
* Convert pseudocode into syntactically correct Java.
* Support common programming constructs.
* Use AI/LLMs to understand ambiguous or natural-language pseudocode.
* Preserve explicitly mentioned imports and function names.
* Generate clean, readable Java code.
* Validate and improve generated code.
* Provide useful error messages when conversion is not possible.

## 🧩 Planned Features

### Basic Programming Constructs

* Variables
* Data types
* Input and output
* Arithmetic operations
* Assignment
* Conditional statements

  * `if`
  * `else if`
  * `else`
* Loops

  * `for`
  * `while`
  * `do-while`
  * for-each
* Functions/methods
* Arrays
* Strings
* Collections
* Basic exception handling

### AI-Based Features

* Natural-language pseudocode understanding
* Flexible syntax interpretation
* Context-aware code generation
* Ambiguity handling
* Code correction
* Error explanation

### Explicit Instruction Preservation

If the pseudocode explicitly mentions an import, the generated Java code should include the corresponding import.

If the pseudocode clearly specifies a function/method name, the generated Java code should preserve that function name.

Example:

```text
Import HashMap

Create a function called findStudent

Use a HashMap to store student details
```

The generated code should retain:

```java
import java.util.HashMap;

static void findStudent(...) {
    ...
}
```

## 🏗️ Proposed Architecture

```text
                ┌─────────────────────┐
                │       User          │
                │     Pseudocode      │
                └──────────┬──────────┘
                           │
                           ▼
                ┌─────────────────────┐
                │  Pseudocode Parser  │
                │   / Preprocessor    │
                └──────────┬──────────┘
                           │
                           ▼
                ┌─────────────────────┐
                │     LLM / AI        │
                │  Intent + Code Gen  │
                └──────────┬──────────┘
                           │
                           ▼
                ┌─────────────────────┐
                │ Java Code Generator │
                └──────────┬──────────┘
                           │
                           ▼
                ┌─────────────────────┐
                │   Validation /      │
                │   Error Handling    │
                └──────────┬──────────┘
                           │
                           ▼
                ┌─────────────────────┐
                │     Java Code       │
                └─────────────────────┘
```

## 🛠️ Technology Stack

### Backend

* Java
* Java-based parsing / processing components
* LLM API

### AI

The project will support a freely available or low-cost LLM API where possible.

Potential options include:

* Llama-based models
* Other open-source LLMs
* Free-tier LLM APIs

### Frontend

The frontend technology will be decided during the initial development phase.

## 📁 Planned Project Structure

```text
pseudocode-to-java/
│
├── README.md
├── src/
│   ├── parser/
│   ├── lexer/
│   ├── generator/
│   ├── validator/
│   ├── ai/
│   └── utils/
│
├── test/
│   ├── parser/
│   ├── generator/
│   └── integration/
│
├── examples/
│   ├── basic/
│   ├── loops/
│   ├── functions/
│   └── collections/
│
└── docs/
```

> The project structure is subject to change as development progresses.

## 🔄 Development Workflow

We will use Git and GitHub for collaborative development.

### Branches

`main` will contain stable code.

Each feature should be developed on a separate branch:

```text
main
│
├── feature/parser
├── feature/lexer
├── feature/code-generator
├── feature/llm-integration
└── feature/frontend
```

### Workflow

```bash
git checkout -b feature/<feature-name>

# Make changes

git add .
git commit -m "Add <feature>"

git push -u origin feature/<feature-name>
```

Create a Pull Request on GitHub and merge into `main` after review.

## 🧪 Testing

The project will include tests for:

* Variable declarations
* Arithmetic operations
* Conditions
* Loops
* Functions
* Arrays
* Collections
* Imports
* User-defined function names
* Invalid pseudocode
* Ambiguous pseudocode
* AI-generated code validation

Example:

```text
Pseudocode
    ↓
Parser
    ↓
Intermediate Representation
    ↓
Java Generator
    ↓
Generated Java
    ↓
Compilation Test
```

## 🗺️ Roadmap

### Phase 1 — Foundation

* [ ] Repository setup
* [ ] Define project architecture
* [ ] Define pseudocode syntax rules
* [ ] Implement basic parser
* [ ] Implement basic Java code generation

### Phase 2 — Core Language Support

* [ ] Variables
* [ ] Operators
* [ ] Conditions
* [ ] Loops
* [ ] Functions
* [ ] Arrays
* [ ] Strings
* [ ] Collections
* [ ] Imports

### Phase 3 — AI Integration

* [ ] Integrate LLM API
* [ ] Design prompts
* [ ] Handle flexible pseudocode
* [ ] Preserve explicit user instructions
* [ ] Handle ambiguous input
* [ ] Implement code correction

### Phase 4 — Validation

* [ ] Java syntax validation
* [ ] Compilation testing
* [ ] Error detection
* [ ] Error messages
* [ ] Automated test suite

### Phase 5 — User Interface

* [ ] Pseudocode editor
* [ ] Java code editor/output
* [ ] Generate button
* [ ] Error display
* [ ] Code download/copy functionality

## 👥 Team

This project is being developed collaboratively using GitHub.

### Contributors

* Shubh Vijayvargiya
* Garvit Aneja
* Navay Seth


## 📌 Current Status

**Project Status:** 🚧 In Development

The initial phase focuses on designing the pseudocode grammar, project architecture, parser, and Java code-generation pipeline.

## 📄 License

License to be decided.
