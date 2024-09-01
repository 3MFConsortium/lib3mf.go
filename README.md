Official lib3mf Go Bindings [v2.3.2]
=====================================

This repository contains the official Go bindings for the lib3mf library.

## Installation

To include lib3mf in your Go project, run the following command:

```shell
go get github.com/3MFConsortium/lib3mf_go/v2@v2.3.2
```


## Usage

Once installed, you can use the lib3mf package in your Go projects as shown below:

```go

import (
	"fmt"
	lib3mf "github.com/3MFConsortium/lib3mf.go/v2"
	"log"
)

func main() {
	wrapper, err := lib3mf.GetWrapper()
	if err != nil {
		log.Fatal("Error loading 3MF library:", err)
	}
}

```

## About GetWrapper()

The `GetWrapper()` function is a convenience method similar to the one in the lib3mf Python bindings. It simplifies handling the library paths for lib3mf, so you do not need to use `LoadLibrary()` manually to load the lib3mf library.
