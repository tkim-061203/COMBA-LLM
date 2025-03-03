allarg=("$@")
tool=$1
restarg=${allarg[@]:2}

docker run -ti --rm -w /work --entrypoint "$tool" -v "$2:/work" deslapp:latest $restarg
# docker run -ti --rm -w /work deslapp:latest