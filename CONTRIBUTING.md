# Contributing to Fuzzy

Hi! First of all, thanks for your interest in contributing. Help in various forms is almost always
needed and in any case appreciated.

## Overview

Fuzzy is written in Python 3.9 with the [discordpy] commands framework. For dependency management we
use [poetry]. 

## Getting Started: Coding

If you want to add a new feature, please start out by creating an issue and opening a discussion
about it. Pull Requests coming out of the blue won't be accepted. If you want to pick up an existing
issue for implementation, leave a note there that you're doing so, so that no one else starts on the
same work as you do accidentally. Then, you can start actually working on it:

### 1. Prerequisites

First you'll want [poetry]. If you don't install Poetry, you will need to check that 
you have [Python 3.9] or later available.

You also need [git] and a Discord bot token, which you can get from the [Applications page] of your Discord
account. You might also need to create a server to test your bot in.

### 2. Forking & Cloning

1. Create a fork, that is, a copy of Fuzzy's repository, for your own GitHub account. There's a
button somewhere on the top right on the repository main site.
2. Clone your fork of Fuzzy into a directory on your PC by following the instructions listed under
"Code"→"Clone" on your fork's GitHub page.

### 3. Initial Setup

1. Switch over into the directory you cloned Fuzzy into and spin up a development shell `poetry shell`.
2. Run `poetry install` to install the dependencies for this project. This might take a while, 
   so grab yourself a cup of tea.
3. Open the file `fuzzy.cfg.example` with your text editor and update at the very least the value of
`discord.token` with the bot token you got from Discord. Without this, your bot won't be able to log
in. You might also want to change other values. Save the file as `fuzzy.cfg` in the same folder.
4. In your development shell, run `python -m fuzzy` to start the bot for the first time. It will
automatically create the needed database.

### 4. Development Workflow

1. Create a new branch for your feature: `git checkout -b just-write-stuff-into-here`. This allows
you to develop your feature concurrently to others working on other things.
2. Once your changes are complete, run `isort fuzzy` and `black fuzzy` in your development shell to
format the codebase, followed by `pylint fuzzy` to see potential issues with your code. Once happy
with the results, stage your changes with git: `git add src/file1 src/file2 src/file_n` and commit
them: `git commit`. Please don't alter the version number of Fuzzy, we'll change it after the merge
is done.
3. Push your work to your fork: `git push origin the-previously-picked-branch-name`. Then, go to the
[pull requests] page and click the button that should appear to create a pull request based on your
recently pushed branch. Write a short summary of your changes; if you think something you've done
warrants extra explanations, do so.
4. Wait for a review. If you want to change more things in your branch, add more commits; don't edit
your previous ones.
5. Wait for your request to be merged into the `main` branch.
6. Reset your working copy by checking out `main`: `git checkout main` and pulling from the main
repository: `git pull upstream main`.

[discordpy]: https://github.com/Rapptz/discord.py/
[Python 3.9]: https://www.python.org/downloads/
[git]: https://git-scm.com/
[poetry]: https://python-poetry.org
[Applications page]: https://discord.com/developers/applications
[pull requests]: https://github.com/The-Valley-Discord/Fuzzy/pulls
