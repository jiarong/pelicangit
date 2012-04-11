#!/usr/bin/python

import SocketServer
import SimpleHTTPServer
import os
import re
import argparse
from pelican import main
from pelican.settings import read_settings
from gitbindings import *

PORT = 8080

GET_RESPONSE_BODY = "<h1>PelicanGit is Running</h1>"
POST_RESPONSE_BODY = "<h1>Pelican Project Rebuilt</h1>"
ERROR_RESPONSE_BODY = "<h1>Error</h1>"

# Look to import these function from pelican module down the line.
# Dupe it here for now for backwards compatibility with older versions of pelican
def parse_arguments():
    parser = argparse.ArgumentParser(description="""A tool to generate a
    static blog, with restructured text input files.""",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)
        
    parser.add_argument(dest='path', nargs='?', help="Path where to find content files", default=None)
    parser.add_argument('-s', '--settings', dest='settings',
        help='The settings of the application.')
        
    return parser.parse_args()

args = parse_arguments()
settings = read_settings(args.settings)

source_repo = GitRepo(
    settings['SOURCE_GIT_REPO'],
    settings['SOURCE_GIT_REMOTE'],
    settings['SOURCE_GIT_BRANCH']
)

deploy_repo = GitRepo(
    settings['DEPLOY_GIT_REPO'],
    settings['DEPLOY_GIT_REMOTE'],
    settings['DEPLOY_GIT_BRANCH']
)

whitelisted_files = settings['GIT_WHITELISTED_FILES']

class GitHookRequestHandler(SimpleHTTPServer.SimpleHTTPRequestHandler):
    def do_GET(self):
        self.do_response(GET_RESPONSE_BODY)

    def do_POST(self):
        try:
            #Hard reset both repos so they match the remote (origin) master branches
            self.hard_reset_repos()
            
            # Git Remove all deploy_repo files (except those whitelisted) and then rebuild with pelican
            self.nuke_git_cwd(deploy_repo) 
            main()

            # Add all files newly created by pelican, then commit and push everything
            deploy_repo.add(['.'])

            commit_message = source_repo.log(['-n1', '--pretty=format:"%h %B"'])
            deploy_repo.commit(commit_message, ['-a'])
            deploy_repo.push([deploy_repo.origin, deploy_repo.master])

            self.do_response(POST_RESPONSE_BODY)
        except Exception as e:
            print e
            
            #In the event of an excepion, hard reset both repos so they match the remote (origin) master branches
            self.hard_reset_repos()
            self.do_response(ERROR_RESPONSE_BODY)


    def do_response(self, resBody):
        self.send_response(200)
        self.send_header("Content-type", "text/html")
        self.send_header("Content-length", len(resBody))
        self.end_headers()
        self.wfile.write(resBody)

    def hard_reset_repos(self):
        source_repo.fetch([source_repo.origin])
        source_repo.reset(['--hard', source_repo.originMaster])
        
        deploy_repo.fetch([deploy_repo.origin])
        deploy_repo.reset(['--hard', deploy_repo.originMaster])

    def nuke_git_cwd(self, git_repo):
        for root, dirs, files in os.walk(git_repo.repoDir):
            #If we are anywhere in the .git directory, then skip this iteration
            if re.match("^.*\.git(/.*)?$", root): continue

            local_dir = root.replace(git_repo.repoDir + "/", "")
            local_dir = local_dir.replace(git_repo.repoDir, "")

            for f in files:
                local_file = os.path.join(local_dir, f)
                if local_file not in whitelisted_files:
                    git_repo.rm(['-r', local_file])

httpd = SocketServer.ForkingTCPServer(('', PORT), GitHookRequestHandler)
print "PelicanGit listening on port", PORT
httpd.serve_forever()
