#!/usr/bin/env python
# Copyright 2014 the V8 project authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import argparse
import os
import sys

from common_includes import *

DEPS_FILE = "DEPS_FILE"
CHROMIUM = "CHROMIUM"

CONFIG = {
  PERSISTFILE_BASENAME: "/tmp/v8-chromium-roll-tempfile",
  DOT_GIT_LOCATION: ".git",
  DEPS_FILE: "DEPS",
}


class Preparation(Step):
  MESSAGE = "Preparation."

  def RunStep(self):
    self.CommonPrepare()


class DetectLastPush(Step):
  MESSAGE = "Detect commit ID of last push to trunk."

  def RunStep(self):
    self["last_push"] = self._options.last_push or self.FindLastTrunkPush(
        include_patches=True)
    self["trunk_revision"] = self.GitSVNFindSVNRev(self["last_push"])
    self["push_title"] = self.GitLog(n=1, format="%s",
                                     git_hash=self["last_push"])


class SwitchChromium(Step):
  MESSAGE = "Switch to Chromium checkout."

  def RunStep(self):
    self["v8_path"] = os.getcwd()
    os.chdir(self._options.chromium)
    self.InitialEnvironmentChecks()
    # Check for a clean workdir.
    if not self.GitIsWorkdirClean():  # pragma: no cover
      self.Die("Workspace is not clean. Please commit or undo your changes.")
    # Assert that the DEPS file is there.
    if not os.path.exists(self.Config(DEPS_FILE)):  # pragma: no cover
      self.Die("DEPS file not present.")


class UpdateChromiumCheckout(Step):
  MESSAGE = "Update the checkout and create a new branch."

  def RunStep(self):
    os.chdir(self._options.chromium)
    self.GitCheckout("master")
    self._side_effect_handler.Command("gclient", "sync --nohooks")
    self.GitPull()
    try:
      # TODO(machenbach): Add cwd to git calls.
      os.chdir(os.path.join(self._options.chromium, "v8"))
      self.GitFetchOrigin()
    finally:
      os.chdir(self._options.chromium)
    self.GitCreateBranch("v8-roll-%s" % self["trunk_revision"])


class UploadCL(Step):
  MESSAGE = "Create and upload CL."

  def RunStep(self):
    os.chdir(self._options.chromium)

    # Patch DEPS file.
    if self._side_effect_handler.Command(
        "roll-dep", "v8 %s" % self["trunk_revision"]) is None:
      self.Die("Failed to create deps for %s" % self["trunk_revision"])

    commit_title = "Update V8 to %s." % self["push_title"].lower()
    sheriff = ""
    if self["sheriff"]:
      sheriff = ("\n\nPlease reply to the V8 sheriff %s in case of problems."
                 % self["sheriff"])
    self.GitCommit("%s%s\n\nTBR=%s" %
                   (commit_title, sheriff, self._options.reviewer))
    self.GitUpload(author=self._options.author,
                   force=True,
                   cq=self._options.use_commit_queue)
    print "CL uploaded."


class SwitchV8(Step):
  MESSAGE = "Returning to V8 checkout."

  def RunStep(self):
    os.chdir(self["v8_path"])


class CleanUp(Step):
  MESSAGE = "Done!"

  def RunStep(self):
    print("Congratulations, you have successfully rolled the push r%s it into "
          "Chromium. Please don't forget to update the v8rel spreadsheet."
          % self["trunk_revision"])

    # Clean up all temporary files.
    Command("rm", "-f %s*" % self._config[PERSISTFILE_BASENAME])


class ChromiumRoll(ScriptsBase):
  def _PrepareOptions(self, parser):
    parser.add_argument("-c", "--chromium", required=True,
                        help=("The path to your Chromium src/ "
                              "directory to automate the V8 roll."))
    parser.add_argument("-l", "--last-push",
                        help="The git commit ID of the last push to trunk.")
    parser.add_argument("--use-commit-queue",
                        help="Check the CQ bit on upload.",
                        default=False, action="store_true")

  def _ProcessOptions(self, options):  # pragma: no cover
    if not options.author or not options.reviewer:
      print "A reviewer (-r) and an author (-a) are required."
      return False

    options.requires_editor = False
    options.force = True
    options.manual = False
    return True

  def _Steps(self):
    return [
      Preparation,
      DetectLastPush,
      DetermineV8Sheriff,
      SwitchChromium,
      UpdateChromiumCheckout,
      UploadCL,
      SwitchV8,
      CleanUp,
    ]


if __name__ == "__main__":  # pragma: no cover
  sys.exit(ChromiumRoll(CONFIG).Run())
