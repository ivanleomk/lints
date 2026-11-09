export interface SourcePosition {
  line: number;
  column: number;
}

export interface SourceLocation {
  start: SourcePosition;
  end: SourcePosition;
}

export interface AstNode {
  type: string;
  loc?: SourceLocation;
  operator?: string;
  name?: string;
  id?: AstNode | null;
  init?: AstNode | null;
  callee?: AstNode;
  object?: AstNode;
  property?: AstNode;
  declaration?: AstNode | null;
  declarations?: AstNode[];
  source?: AstNode | null;
  body?: AstNode[];
  typeAnnotation?: AstNode;
  typeName?: AstNode;
}

export interface RuleContext {
  filename?: string;
  report(descriptor: { node: AstNode; message: string }): void;
}

export interface RuleDefinition {
  meta: {
    type: "problem" | "suggestion" | "layout";
    docs: {
      description: string;
    };
  };
  create(context: RuleContext): Record<string, (node: AstNode) => void>;
}
