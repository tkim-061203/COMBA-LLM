#-------------------------------------------------------------------------
# Project metadata
#-------------------------------------------------------------------------

m4_define( proj_name,         [COMBA LLM Project])
m4_define( proj_maintainer,   [Vu-Minh-Thanh Nguyen nvmthanh@hcmus.edu.vn])
m4_define( proj_abbreviation, [comba-llm-p])

#-------------------------------------------------------------------------
# Project version information
#-------------------------------------------------------------------------
# Version information is meant to be managed through a version control
# system's tags and revision numbers. In a working copy the version will
# not be defined here (you should just use the version control system's
# mechanisms). When we make a distribution then we can set the version
# here as formed by the scripts/vcs-version.sh script so that the
# distribution knows what version it came from. If you are not using
# version control then it is fine to set this directly.

m4_define( proj_version, [0.0.0])

#-------------------------------------------------------------------------
# Setup
#-------------------------------------------------------------------------

AC_INIT(proj_name,proj_version,proj_maintainer,proj_abbreviation)
AC_CONFIG_SRCDIR([run.py])

AC_ARG_WITH(temperature,
  AS_HELP_STRING([--with-temperature],[Temperature]),
  [temperature="${with_temperature}"],
  [temperature="0.85"])

AC_SUBST([temperature])
AC_MSG_NOTICE([using temperature: ${temperature}])

#-------------------------------------------------------------------------
# --with-samples
#-------------------------------------------------------------------------

AC_ARG_WITH(samples,
  AS_HELP_STRING([--with-samples],[Number of samples for each problem]),
  [samples="${with_samples}"],
  [samples="1"])

AC_SUBST([samples])
AC_MSG_NOTICE([using samples: ${samples}])

#-------------------------------------------------------------------------
# --with-examples
#-------------------------------------------------------------------------

AC_ARG_WITH(examples,
  AS_HELP_STRING([--with-examples],[Number of examples for ICL context]),
  [examples="${with_examples}"],
  [examples="0"])

AC_SUBST([examples])
AC_MSG_NOTICE([using examples: ${examples}])

#-------------------------------------------------------------------------
# --with-model
#-------------------------------------------------------------------------

AC_ARG_WITH(model,
  AS_HELP_STRING([--with-model],[Large language model to use]),
  [model="${with_model}"],
  [model="manual_Mistral_7B"])

AC_SUBST([model])
AC_MSG_NOTICE([using model: ${model}])

#-------------------------------------------------------------------------
# --with-model-manual 
#-------------------------------------------------------------------------

AC_ARG_WITH(model-manual,
  AS_HELP_STRING([--with-model-manual],[Base URL of model]),
  [model_manual="${with_model_manual}"],
  [model_manual=True])

AC_SUBST([model_manual])
AC_MSG_NOTICE([using model-manual: ${model_manual}])

#-------------------------------------------------------------------------
# --with-task
#-------------------------------------------------------------------------

AC_ARG_WITH(task,
  AS_HELP_STRING([--with-task],[Task to execute: spec-to-rtl or code-complete-iccad2023]),
  [task="${with_task}"],
  [task="code-complete-iccad2023"])

AC_SUBST([task])
AC_MSG_NOTICE([using task: ${task}])

#-------------------------------------------------------------------------
# --with-model-manual 
#-------------------------------------------------------------------------

AC_ARG_WITH(generatecodeonly,
  AS_HELP_STRING([--with-generatecodeonly],[Generate code only, no post-prosessing]),
  [generatecodeonly="True"],
  [generatecodeonly=""])

AC_SUBST([generatecodeonly])
AC_MSG_NOTICE([using generatecodeonly: ${generatecodeonly}])

#-------------------------------------------------------------------------
# Output
#-------------------------------------------------------------------------

AC_CONFIG_FILES([Makefile])
AC_OUTPUT