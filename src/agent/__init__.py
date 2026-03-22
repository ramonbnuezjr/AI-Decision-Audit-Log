"""Monolithic agent — routes LLM calls through AuditLogger to all providers."""

from src.agent.agent import Agent

__all__ = ["Agent"]
