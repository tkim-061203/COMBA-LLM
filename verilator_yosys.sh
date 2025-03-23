allarg=("$@")
tool=$1
restarg=${allarg[@]:2}

docker run -ti --rm -w /work --entrypoint "$tool" -v "$2:/work" -v /etc/passwd:/etc/passwd:ro -v /etc/group:/etc/group:ro -v $HOME/.cache:$HOME/.cache --user $(id -u):$(id -g) deslapp:latest $restarg
# docker run -ti --rm -w /work deslapp:latest